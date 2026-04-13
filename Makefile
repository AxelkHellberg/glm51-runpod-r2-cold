IMAGE_NAME ?= glm51-runpod-r2-cold:local
PROMPT ?= hello
CONFIRM ?=
LIVE_ACTION_ACK ?=

.DEFAULT_GOAL := help

.PHONY: help sync test doctor build plan live-up live-test live-down nuke-project

help:
	@printf "Targets:\\n"
	@printf "  make sync                     Install the local Python environment with uv\\n"
	@printf "  make test                     Run the fast local test suite\\n"
	@printf "  make doctor                   Validate env, Runpod access, and R2 access\\n"
	@printf "  make build IMAGE_NAME=...     Build the Docker image locally\\n"
	@printf "  make plan                     Print the exact Runpod payload without provisioning\\n"
	@printf "  make live-up                  Create or reuse the Pod after the live-action gate\\n"
	@printf "  make live-test PROMPT=...     Send a prompt to the live OpenAI-compatible endpoint\\n"
	@printf "  make live-down                Destroy the tracked Pod\\n"
	@printf "  make nuke-project CONFIRM=glm51-runpod-r2-cold\\n"

sync:
	uv sync

test:
	uv run pytest

doctor:
	uv run python scripts/doctor.py

build:
	docker build -f docker/Dockerfile -t $(IMAGE_NAME) .

plan:
	uv run python scripts/create_runpod_pod.py --plan

live-up:
	uv run python scripts/create_runpod_pod.py --live-action-ack "$(LIVE_ACTION_ACK)" && uv run python scripts/wait_for_pod.py

live-test:
	uv run python scripts/test_prompt.py --prompt "$(PROMPT)"

live-down:
	uv run python scripts/terminate_pod.py

nuke-project:
	uv run python scripts/cleanup_project_resources.py --confirm "$(CONFIRM)"
