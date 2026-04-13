from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import boto3
from botocore.exceptions import ClientError


class R2Storage:
    def __init__(self, account_id: str, bucket: str, access_key_id: str, secret_access_key: str) -> None:
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    def head_bucket(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)

    def object_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def read_json(self, key: str) -> dict[str, Any] | None:
        if not self.object_exists(key):
            return None
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)

    def download_manifest_tree(self, manifest: dict[str, Any], artifact_prefix: str, target_root: Path) -> None:
        target_root.mkdir(parents=True, exist_ok=True)
        files = manifest.get("files", [])
        for item in files:
            relative_path = item["relative_path"]
            key = f"{artifact_prefix}/{relative_path}"
            target_path = target_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.client.download_file(self.bucket, key, str(target_path))

    def upload_model_tree(
        self,
        source_root: Path,
        manifest_key: str,
        artifact_prefix: str,
        model_id: str,
        exclude_paths: Iterable[Path],
    ) -> dict[str, Any]:
        exclude_set = {path.resolve() for path in exclude_paths}
        files: list[dict[str, Any]] = []
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if any(resolved == exclude_path or exclude_path in resolved.parents for exclude_path in exclude_set):
                continue
            relative_path = path.relative_to(source_root).as_posix()
            object_key = f"{artifact_prefix}/{relative_path}"
            self.client.upload_file(str(path), self.bucket, object_key)
            files.append(
                {
                    "relative_path": relative_path,
                    "size_bytes": path.stat().st_size,
                    "object_key": object_key,
                }
            )

        etag_map = self.list_object_etags(artifact_prefix)
        for item in files:
            item["etag"] = etag_map.get(item["object_key"])

        manifest = {
            "model_id": model_id,
            "artifact_prefix": artifact_prefix,
            "file_count": len(files),
            "total_size_bytes": sum(item["size_bytes"] for item in files),
            "files": files,
        }
        self.client.put_object(
            Bucket=self.bucket,
            Key=manifest_key,
            Body=(json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            ContentType="application/json",
        )
        return manifest

    def list_object_etags(self, prefix: str) -> dict[str, str]:
        paginator = self.client.get_paginator("list_objects_v2")
        result: dict[str, str] = {}
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                result[obj["Key"]] = obj.get("ETag", "").strip('"')
        return result

    def delete_prefix(self, prefix: str) -> int:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[dict[str, str]] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append({"Key": obj["Key"]})
        deleted = 0
        for index in range(0, len(keys), 1000):
            batch = keys[index : index + 1000]
            self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch})
            deleted += len(batch)
        return deleted

    def list_prefix(self, prefix: str) -> list[dict[str, Any]]:
        paginator = self.client.get_paginator("list_objects_v2")
        items: list[dict[str, Any]] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            items.extend(page.get("Contents", []))
        return items


def bytes_to_gib(total_bytes: int) -> float:
    return total_bytes / math.pow(1024, 3)

