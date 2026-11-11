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


def _detect_alarms_api(log_path: Path, c: float, bets: tuple[float, ...], weights) -> list[str]:
    """The ``detect`` loop of the CLI, written with the Python API."""
    from azarovo_martingale import MixtureGrowthDetector, read_log

    out: list[str] = []
    log = read_log(log_path)
    for name in sorted(log.vms):
        vm = log.vms[name]
        det = MixtureGrowthDetector(c, 0.01, bets, weights)
        for k in range(1, len(vm)):
            if det.update(vm.used[k] - vm.used[k - 1], vm.time[k] - vm.time[k - 1]):
                out.append(f"{name}\t{vm.time[k]:g}")
                det.reset()
    return out


@pytest.fixture
def steep_csv(tmp_path: Path) -> Path:
    """A steady rise of 30 MiB per step: the mixture detector alarms on it."""
    lines = ["time,vm,used_mb,free_mb"]
    for t in range(80):
        lines.append(f"{t},vm-b,{1000 + 30 * t},{2500 - 30 * t}")
    path = tmp_path / "steep.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_detect_bets_and_weights_reach_the_detector(
    steep_csv: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # One bet of weight 1 is a single-bet mixture: the CLI must match the API exactly.
    argv = ["detect", str(steep_csv), "--c", "50", "--detector", "mixture"]
    assert main([*argv, "--bets", "0.5", "--weights", "1"]) == 0
    cli = capsys.readouterr().out.strip().splitlines()
    assert cli == _detect_alarms_api(steep_csv, 50.0, (0.5,), (1.0,))
    assert cli, "the steep rise must raise at least one alarm"


def test_detect_weights_are_normalised(steep_csv: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["detect", str(steep_csv), "--c", "15", "--detector", "mixture", "--bets", "0.2,0.8"]
    assert main([*args, "--weights", "1,3"]) == 0
    raw = capsys.readouterr().out
    assert main([*args, "--weights", "0.25,0.75"]) == 0
    assert capsys.readouterr().out == raw
    assert raw.strip(), "the normalised and raw weights must both alarm"


def test_analyze_bets_and_weights_are_reported(
    log_csv: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    args = ["analyze", str(log_csv), "--out", str(out), "--json", "--bets", "0.2,0.8"]
    assert main([*args, "--weights", "1,3"]) == 0
    data = json.loads(capsys.readouterr().out.split("Results saved")[0])
    assert data["options"]["bets"] == [0.2, 0.8]
    assert data["options"]["weights"] == pytest.approx([0.25, 0.75])
    assert main(["analyze", str(log_csv), "--out", str(out), "--json"]) == 0
    default = json.loads(capsys.readouterr().out.split("Results saved")[0])
    assert default["options"]["bets"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    assert default["options"]["weights"] is None


@pytest.mark.parametrize(
    "argv",
    [
        [
            "detect",
            "LOG",
            "--c",
            "15",
            "--detector",
            "mixture",
            "--bets",
            "0.2,0.8",
            "--weights",
            "1,1,2",
        ],
        ["analyze", "LOG", "--bets", "0.2,0.8", "--weights", "1,1,2"],
        ["analyze", "LOG", "--weights", "1,1"],
        ["detect", "LOG", "--c", "15", "--detector", "mixture", "--bets", "0.2,x"],
        ["detect", "LOG", "--c", "15", "--detector", "mixture", "--bets", ""],
        ["detect", "LOG", "--c", "15", "--detector", "mixture", "--weights", "0,0"],
        ["detect", "LOG", "--c", "15", "--detector", "mixture", "--weights", "-1,2"],
        ["detect", "LOG", "--c", "15", "--detector", "mixture", "--bets", "1.5"],
        ["detect", "LOG", "--c", "15", "--detector", "cusum", "--bets", "0.2,0.8"],
    ],
    ids=[
        "length-mismatch-detect",
        "length-mismatch-analyze",
        "weights-without-bets",
        "not-a-number",
        "empty-list",
        "zero-sum",
        "negative-weight",
        "bet-out-of-range",
        "bets-with-cusum",
    ],
)
def test_bad_bets_and_weights_exit_with_status_two(
    log_csv: Path, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [str(log_csv) if a == "LOG" else a for a in argv]
    code = None
    try:
        code = main(argv)
    except SystemExit as exc:  # argparse errors
        code = exc.code
    assert code == 2
    assert capsys.readouterr().err
