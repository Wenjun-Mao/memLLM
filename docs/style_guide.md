## Development Conventions

*   **Best Practices First:** Always implement the most robust, idiomatic, modularized and maintainable solution from the start. Avoid "quick fixes" that compromise code integrity or architectural clarity.
*   **Modern Code Style:** The project uses modern Python (3.12+) and library (SQLAlchemy 2.0, Pydantic v2) features. This includes using `list` and `|` for typing instead of `typing.List` and `typing.Optional`.
*   **Package Management:** Modern services use `uv` for fast dependency management and virtual environments.
*   **Settings:** 
    *   Use `pydantic-settings` via `BaseSettings`.
    *   Prioritize Docker secrets (`/run/secrets`) > Environment variables > Defaults.
    *   Prefix environment variables with the service name (e.g., `S2_RABBITMQ_URL`).
*   **Logging:** Use `loguru` for structured logging.
*   **Testing:** `pytest` is the standard test runner.

## Code Style Preferences

*   **Self-Documenting Code:** Prioritize code that is readable and self-documenting to aid long-term maintenance.
*   **Explanatory Comments:** For complex functions or methods, add comments that explain the logic. A preferred style is a high-level "map" in the docstring that outlines the steps, with "step" markers in the code itself.

