"""The package is typed, standard-library only at run time, and its names are exported."""

import importlib
import tomllib
from pathlib import Path

import azarovo_martingale

ROOT = Path(__file__).parent.parent


def test_version_matches_pyproject() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert azarovo_martingale.__version__ == data["project"]["version"]


def test_core_has_no_runtime_dependencies() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []


def test_all_names_are_importable() -> None:
    for name in azarovo_martingale.__all__:
        assert getattr(azarovo_martingale, name) is not None


def test_py_typed_marker() -> None:
    assert (ROOT / "src" / "azarovo_martingale" / "py.typed").exists()
    importlib.import_module("azarovo_martingale.cli")
