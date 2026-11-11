# Publishing azarovo-martingale

[Русская версия](../ru/publishing.md)

Publishing is manual; the project has no CI or release automation.

## Before a release

1. Check that `version` in `pyproject.toml`, `__version__` in
   `src/azarovo_martingale/__init__.py`, the `## [x.y.z]` heading of `CHANGELOG.md`,
   and `version` in `CITATION.cff` agree.
2. Run the checks:

   ```sh
   uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
   ```

3. Build the distributions and check them:

   ```sh
   rm -rf dist && uv build
   uvx twine check dist/*
   ```

## Upload to PyPI

1. Create an API token on PyPI and pass it through the environment, for example
   `export UV_PUBLISH_TOKEN=pypi-...` (do not commit it).
2. Upload: `uv publish`.

## Tag and push

```sh
git tag v0.0.1
git push origin main --tags
```

The repository is https://github.com/89605502155/azarovo-martingale. The commit-message
rule (subject of at most 8 characters, no body) is enforced locally by the
`commit-msg` hook; install it once per clone with `scripts/install_hooks.sh`.
