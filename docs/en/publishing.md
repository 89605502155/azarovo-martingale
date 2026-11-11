# Publishing azarovo-martingale

[Русская версия](../ru/publishing.md)

## Before a release

1. Update `version` in `pyproject.toml`, `__version__` in
   `src/azarovo_martingale/__init__.py`, `CHANGELOG.md`, and `version` and
   `date-released` in `CITATION.cff`.
2. Run the checks:

   ```sh
   uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
   ```

3. Build and check the distributions:

   ```sh
   rm -rf dist && uv build
   uvx twine check dist/*
   ```

## GitHub and PyPI (trusted publishing)

1. Create the repository `89605502155/azarovo-martingale`, push `main`, and install the
   commit hook in each clone with `scripts/install_hooks.sh`.
2. On PyPI, add a trusted publisher for the project `azarovo-martingale`: owner
   `89605502155`, repository `azarovo-martingale`, workflow `publish.yml`, environment
   `pypi`.
3. Tag the release (`git tag v0.1.0 && git push origin v0.1.0`). The workflow
   `.github/workflows/publish.yml` builds the distributions and publishes them
   without a token.

The commit-message rule (subject of at most 8 characters, no body) is enforced
by `scripts/check_commit_msg.py` in the hook and in the CI workflow.
