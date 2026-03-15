# Reference: UV Monorepo Notes

The active workspace setup notes currently live at [../uv_monorepo_notes.md](../uv_monorepo_notes.md).

The key takeaways already applied in this repo are:

- the workspace root has its own unique project name
- local workspace packages are resolved through `[tool.uv.sources]`
- pytest uses `--import-mode=importlib`
