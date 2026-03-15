from __future__ import annotations

import httpx


def main() -> None:
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0) as client:
        response = client.post("/seed/characters")
        response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
