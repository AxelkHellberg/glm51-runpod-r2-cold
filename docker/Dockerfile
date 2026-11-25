FROM vllm/vllm-openai:glm51

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
# Runtime paths resolve config, scripts, and state relative to the source tree.
RUN pip install --no-cache-dir -e .

COPY config /app/config
COPY scripts /app/scripts
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

RUN chmod +x /app/docker/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=20 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]

