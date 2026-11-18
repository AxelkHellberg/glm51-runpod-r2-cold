# glm51-runpod-r2-cold

Cost-aware infrastructure workflow for serving `zai-org/GLM-5.1-FP8` on Runpod with `vLLM`, using Cloudflare R2 as the only persistent artifact layer.

This project is intentionally narrow: it optimizes for near-zero idle compute cost, not for the fastest possible startup. The pod is created on demand, restores or downloads the model into its final path, serves an OpenAI-compatible API, and is then deleted completely.

## Why this exists

Large open-weight models are expensive to keep warm. This repository explores a pragmatic tradeoff:

- no always-on pod
- no Runpod network volume
- no serverless endpoint
- one cold artifact cache in R2
- one disposable pod per session

That design keeps idle cost effectively at zero, but it makes the first successful boot slow and operationally sensitive to GPU availability.

## What the repo demonstrates

- direct Runpod REST orchestration from Python with `httpx`
- disk-aware model bootstrap for a `~700 GiB` artifact footprint
- R2 manifest-based restore and mirror flow with `boto3`
- containerized `vLLM` serving based on the official `vllm/vllm-openai:glm51` image
- explicit safety rails for destructive actions and live cloud provisioning

## Serving shape

- Model: `zai-org/GLM-5.1-FP8`
- Served model name: `glm-5.1-fp8`
- Tensor parallel size: `8`
- Tool-call parser: `glm47`
- Reasoning parser: `glm45`
- Auto tool choice: enabled
- Default GPU target: `8x NVIDIA H200`

Anything other than `8x NVIDIA H200` should be treated as experimental.

## Cold-start flow

1. `make doctor` validates Runpod access, R2 access, image config, and cache state.
2. `make plan` prints the exact pod payload without provisioning anything.
3. `make live-up` creates a disposable Runpod pod only after an explicit gate.
4. The entrypoint restores the model from R2 if a manifest exists. Otherwise it downloads directly from Hugging Face into the final model path and optionally mirrors the artifacts back to R2.
5. `vLLM` serves on port `8000` using the OpenAI-compatible API.
6. `make live-down` destroys the pod completely.

## Validation status

What has been validated in this repo:

- local environment install with `uv`
- Python package import and script compilation
- exact Runpod payload generation
- Runpod API preflight and project-scoped cleanup logic
- live pod create and delete flow

What is still operationally constrained:

- the official `8x H200` shape is expensive and can be hard to rent on demand
- the first successful cold boot without an R2 cache is slow because the model is very large
- this is not a benchmarked production deployment

## Known limitations

- This repository is model-specific rather than a generic deployment framework.
- Automated tests cover the configuration and command-building logic, not live cloud execution.
- Runpod capacity is an external dependency. Even correct requests can fail when the requested GPU shape is unavailable.
- For this model size, “low idle cost” does not mean “low runtime cost.” The design saves money when idle, not necessarily while the pod is running.

## Project structure

- `config/`: default settings and the `r2-cold` mode definition
- `docker/`: Docker build and container entrypoint
- `scripts/`: operator-facing commands
- `src/glm51_runpod_r2_cold/`: shared config, Runpod API, R2, bootstrap, and state logic
- `tests/`: fast unit tests for config and serving-shape logic

## Environment

Copy `.env.example` to `.env` and fill the required values:

```bash
cp .env.example .env
```

The repository expects at least:

- `RUNPOD_API_KEY`
- `RUNPOD_IMAGE_NAME`
- `R2_ACCOUNT_ID`
- `R2_BUCKET`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

Optional values:

- `RUNPOD_CONTAINER_REGISTRY_AUTH_ID` for private registry pulls
- `HF_TOKEN` for gated or rate-limited Hugging Face downloads

## Quickstart

```bash
make sync
make test
make doctor
make plan
```

For a real deployment:

```bash
make build IMAGE_NAME="$RUNPOD_IMAGE_NAME"
# push the image to your registry
# set LIVE_DEPLOY=1 in .env
make live-up
make live-up LIVE_ACTION_ACK=DONE
make live-test PROMPT="Explain WireGuard vs OpenVPN in modern production terms"
make live-down
```

## Commands

- `make sync`: install the local Python environment and the `dev` extra with `uv`
- `make test`: install the `dev` extra if needed and run the fast unit test suite with the project Python
- `make doctor`: validate env, Runpod access, and R2 access
- `make build IMAGE_NAME=...`: build the Docker image locally
- `make plan`: print the exact Runpod pod payload
- `make live-up`: create or reuse the project pod after the live-action gate
- `make live-test PROMPT="..."`: send a prompt to the live OpenAI-compatible endpoint
- `make live-down`: destroy the tracked pod
- `make nuke-project CONFIRM=glm51-runpod-r2-cold`: delete only project-owned pods, mirrored R2 objects, and local state

## Safety

- No Runpod templates are created or used.
- No Runpod network volumes are created or used.
- Cleanup targets only pod names that match the project prefix.
- Local runtime state lives under `.state/` and is not committed.
- The R2 manifest is written after uploads complete, so partial mirrors are not exposed as valid caches.

## Portfolio note

This is best read as an AI infra / LLMOps project, not as an end-user app. It shows system design, cost tradeoff thinking, cloud automation, and operational safety around large-model inference.
