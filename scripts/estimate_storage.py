#!/usr/bin/env python3
from __future__ import annotations

import json

from huggingface_hub import HfApi

from glm51_runpod_r2_cold.config import load_app_config


def main() -> None:
    config = load_app_config()
    api = HfApi(token=config.hf_token)
    info = api.model_info(config.model_id, files_metadata=True)
    files = []
    total_size_bytes = 0
    for sibling in info.siblings:
        size = getattr(sibling, "size", None) or 0
        total_size_bytes += size
        files.append({"path": sibling.rfilename, "size_bytes": size})

    total_gib = total_size_bytes / (1024**3)
    estimated_r2_storage_usd_per_month = total_gib * 0.015
    print(
        json.dumps(
            {
                "model_id": config.model_id,
                "file_count": len(files),
                "total_size_bytes": total_size_bytes,
                "total_size_gib": round(total_gib, 2),
                "estimated_r2_storage_usd_per_month_at_0_015_per_gib": round(estimated_r2_storage_usd_per_month, 2),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

