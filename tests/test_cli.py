"""Command-line tool: the three commands and their error exits."""

import json
import random
from pathlib import Path

import pytest

from azarovo_martingale.cli import main


@pytest.fixture
def log_csv(tmp_path: Path) -> Path:
    rng = random.Random(3)
    lines = ["time,vm,used_mb,free_mb,phase"]
    used = 1000.0
    for t in range(600):
        growth = 400 <= t < 440
        used += max(-30.0, min(30.0, rng.gauss(20.0 if growth else 0.0, 8.0)))
        phase = "growth" if growth else "calm"
        lines.append(f"{t},vm-a,{used:.2f},{2500 - used:.2f},{phase}")
    path = tmp_path / "log.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_interval_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["interval", "512", "20"]) == 0
    assert capsys.readouterr().out.strip() == "71"
    assert main(["interval", "512", "20", "--n-max", "60"]) == 0
    assert capsys.readouterr().out.strip() == "60"


def test_detect_command_prints_alarms(log_csv: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # With a fixed bet the long calm period drives the capital down (section 3.5 of the article),
    # so the CUSUM variant is the one that catches the 40 s rise in this log.
    assert main(["detect", str(log_csv), "--c", "15", "--vm", "vm-a", "--detector", "cusum"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out
    assert all(line.startswith("vm-a\t") for line in out)
    assert main(["detect", str(log_csv), "--c", "15", "--detector", "mixture"]) == 0


def test_analyze_command_writes_outputs(
    log_csv: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    assert main(["analyze", str(log_csv), "--out", str(out), "--fixed", "1,5"]) == 0
    text = capsys.readouterr().out
    assert "## VM vm-a" in text
    assert "Results saved to" in text
    assert (out / "summary.md").exists()
    data = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert data["vms"][0]["vm"] == "vm-a"
    assert main(["analyze", str(log_csv), "--out", str(out), "--json"]) == 0
    assert json.loads(capsys.readouterr().out.split("Results saved")[0])["vms"]


def test_analyze_needs_reserve_without_free_column(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "nofree.csv"
    path.write_text(
        "time,vm,used_mb\n" + "".join(f"{t},a,{t}\n" for t in range(30)), encoding="utf-8"
    )
    assert main(["analyze", str(path), "--out", str(tmp_path / "o")]) == 2
    assert "--reserve" in capsys.readouterr().err
    assert main(["analyze", str(path), "--out", str(tmp_path / "o"), "--reserve", "500"]) == 0


def test_errors_exit_with_status_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "none.csv"
    assert main(["analyze", str(missing)]) == 2
    assert "error" in capsys.readouterr().err
    assert main(["detect", str(missing), "--c", "1"]) == 2
