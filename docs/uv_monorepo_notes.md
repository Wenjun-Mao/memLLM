# 3 Things I Wish I Knew Before Setting Up a UV Workspace

Here is a lean, technical summary of the core concepts for setting up a Python monorepo with `uv` workspaces.

## 1. Root Workspace Naming
Even when configuring a virtual root workspace (`package = false`), it still requires a `[project] name` in the `pyproject.toml` file. This root name must be unique and cannot match the name of any member package, otherwise `uv sync` will fail with an error stating two workspace members share the same name.
- **Fix:** Assign a distinct name to the root (e.g., `name = "my-app-workspace"`) and place development dependencies in `[dependency-groups]` rather than `[project.dependencies]`.

## 2. Inter-Package Dependencies
When one package in your workspace depends on another, standard dependency declarations are insufficient. You must explicitly tell `uv` to resolve the dependency locally using the `[tool.uv.sources]` table, which automatically installs the local package in editable mode.
- **Fix:** Keep standard dependencies in `[project.dependencies]` for standard tool compliance, but add `{ workspace = true }` under `[tool.uv.sources]`. 
```toml
[tool.uv.sources]
my-app = { workspace = true }
```

## 3. Pytest Collision Fix
When testing a monorepo, identically named test files across different packages (e.g., multiple `test_helpers.py` files) will crash `pytest` because its default `prepend` import mode treats them as the same module. Avoid adding `__init__.py` files to test directories as a workaround, as this can silently run the wrong tests under the new mode.
- **Fix:** Change the import mode to `importlib` in the root `pyproject.toml`.
```toml
[tool.pytest.ini_options]
addopts = "--import-mode=importlib"
```
