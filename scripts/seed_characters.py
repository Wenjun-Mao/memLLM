from __future__ import annotations

import argparse
import os

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed character manifests through the memLLM API.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("MEMLLM_API_BASE_URL", "http://127.0.0.1:8000"),
        help="Base URL of the memLLM API.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        response = client.post("/seed/characters")
        response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
