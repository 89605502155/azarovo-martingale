# Публикация azarovo-martingale

[English version](../en/publishing.md)

## Перед выпуском

1. Обновите `version` в `pyproject.toml`, `__version__` в
   `src/azarovo_martingale/__init__.py`, `CHANGELOG.md`, а также `version` и
   `date-released` в `CITATION.cff`.
2. Прогоните проверки:

   ```sh
   uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
   ```

3. Соберите и проверьте дистрибутивы:

   ```sh
   rm -rf dist && uv build
   uvx twine check dist/*
   ```

## GitHub и PyPI (доверенная публикация)

1. Создайте репозиторий `89605502155/azarovo-martingale`, отправьте `main` и установите
   хук сообщений коммитов в каждом клоне командой `scripts/install_hooks.sh`.
2. На PyPI добавьте доверенного издателя для проекта `azarovo-martingale`: владелец
   `89605502155`, репозиторий `azarovo-martingale`, рабочий процесс `publish.yml`,
   окружение `pypi`.
3. Поставьте тег (`git tag v0.1.0 && git push origin v0.1.0`). Рабочий процесс
   `.github/workflows/publish.yml` соберёт дистрибутивы и опубликует их без токена.

Правило сообщений коммитов (тема не длиннее 8 символов, без тела) проверяют
`scripts/check_commit_msg.py` в хуке и в рабочем процессе CI.
