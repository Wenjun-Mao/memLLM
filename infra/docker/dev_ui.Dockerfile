FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_LINK_MODE=copy     UV_COMPILE_BYTECODE=1

WORKDIR /app
COPY . .
RUN uv sync --frozen --all-packages --no-dev

EXPOSE 8501
CMD ["uv", "run", "--no-sync", "--package", "memllm-dev-ui", "memllm-dev-ui"]
