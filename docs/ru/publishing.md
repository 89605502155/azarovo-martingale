# Публикация azarovo-martingale

[English version](../en/publishing.md)

Публикация выполняется вручную; CI и автоматизация выпусков в проекте нет.

## Перед выпуском

1. Проверьте, что `version` в `pyproject.toml`, `__version__` в
   `src/azarovo_martingale/__init__.py`, заголовок `## [x.y.z]` в `CHANGELOG.md` и
   `version` в `CITATION.cff` совпадают.
2. Прогоните проверки:

   ```sh
   uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
   ```

3. Соберите дистрибутивы и проверьте их:

   ```sh
   rm -rf dist && uv build
   uvx twine check dist/*
   ```

## Загрузка на PyPI

1. Создайте токен API на PyPI и передайте его через окружение, например
   `export UV_PUBLISH_TOKEN=pypi-...` (не коммитьте его).
2. Загрузка: `uv publish`.

## Метка и отправка

```sh
git tag v0.0.1
git push origin main --tags
```

Репозиторий: https://github.com/89605502155/azarovo-martingale. Правило сообщений коммитов
(тема не длиннее 8 символов, без тела) проверяет локально хук `commit-msg`; установите
его один раз в каждом клоне командой `scripts/install_hooks.sh`.
