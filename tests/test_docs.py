"""The Python code blocks of the README files and the guides run without errors.

All ``python`` code blocks of a document are executed in order, in one namespace,
in a temporary working directory.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DOCUMENTS = [
    ROOT / "README.md",
    ROOT / "README.ru.md",
    ROOT / "docs" / "en" / "quickstart.md",
    ROOT / "docs" / "ru" / "quickstart.md",
    ROOT / "docs" / "en" / "api.md",
    ROOT / "docs" / "ru" / "api.md",
]
BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_code_blocks_run(
    document: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocks = BLOCK.findall(document.read_text(encoding="utf-8"))
    assert blocks, f"{document} has no Python examples"
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {"__name__": "__doc__"}
    for code in blocks:
        exec(compile(code, str(document), "exec"), namespace)  # noqa: S102
    capsys.readouterr()
