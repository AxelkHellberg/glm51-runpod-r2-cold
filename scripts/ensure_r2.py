#!/usr/bin/env python3
from __future__ import annotations

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.console import print_report_line
from glm51_runpod_r2_cold.r2_storage import R2Storage


def main() -> None:
    config = load_app_config()
    r2 = R2Storage(
        account_id=config.r2.account_id or "",
        bucket=config.r2.bucket or "",
        access_key_id=config.r2.access_key_id or "",
        secret_access_key=config.r2.secret_access_key or "",
    )
    r2.head_bucket()
    print_report_line("Bucket", "OK", config.r2.bucket or "<missing>")
    print_report_line("Manifest key", "OK", config.manifest_key)
    print_report_line("Manifest exists", "OK" if r2.object_exists(config.manifest_key) else "WARN", str(r2.object_exists(config.manifest_key)))


if __name__ == "__main__":
    main()

