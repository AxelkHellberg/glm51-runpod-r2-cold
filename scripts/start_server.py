#!/usr/bin/env python3
from __future__ import annotations

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.server import exec_vllm


def main() -> None:
    exec_vllm(load_app_config())


if __name__ == "__main__":
    main()

