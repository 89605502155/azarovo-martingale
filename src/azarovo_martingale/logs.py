"""Reading monitoring logs: CSV files with one row per sample of one VM.

Columns: ``time`` and ``vm`` and ``used_mb`` are required; ``free_mb`` (the reserve
``R``) and ``phase`` (``growth`` marks a period of growth) are optional. The
delimiter (comma, semicolon or tab) is detected and a decimal comma is accepted.
See ``docs/en/log-format.md``.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["GROWTH_PHASE", "MonitoringLog", "VmLog", "read_log"]

GROWTH_PHASE = "growth"
"""Value of the ``phase`` column that marks a period of growth."""

_REQUIRED = ("time", "vm", "used_mb")


@dataclass
class VmLog:
    """Samples of one VM, sorted by time, duplicates in time removed.

    Attributes
    ----------
    name : str
        Identifier of the VM (the ``vm`` column).
    time : list of float
        Timestamps, strictly increasing.
    used : list of float
        Memory used, MiB.
    free : list of float
        Free reserve, MiB; ``nan`` where the log has no ``free_mb`` column.
    growth : list of bool
        ``True`` where the ``phase`` column is ``growth``; all ``False`` without it.
    duplicates : int
        Number of samples dropped because their time repeated an earlier one.
    """

    name: str
    time: list[float] = field(default_factory=list)
    used: list[float] = field(default_factory=list)
    free: list[float] = field(default_factory=list)
    growth: list[bool] = field(default_factory=list)
    duplicates: int = 0

    def __len__(self) -> int:
        """Return the number of samples."""
        return len(self.time)


@dataclass
class MonitoringLog:
    """A parsed monitoring log.

    Attributes
    ----------
    vms : dict of str to VmLog
        Samples per VM, in the order of their names in the file.
    has_free : bool
        Whether the file has a ``free_mb`` column.
    has_phase : bool
        Whether the file has a ``phase`` column.
    """

    vms: dict[str, VmLog]
    has_free: bool
    has_phase: bool


def _number(text: str) -> float:
    return float(text.strip().replace(",", "."))


def read_log(path: str | Path, *, sep: str | None = None) -> MonitoringLog:
    r"""Read a monitoring log from a CSV file.

    Parameters
    ----------
    path : str or Path
        Path of the CSV file with a header line.
    sep : str, optional
        Delimiter; detected automatically from ``, ; <tab>`` by default.

    Returns
    -------
    MonitoringLog
        The samples grouped by VM.

    Raises
    ------
    ValueError
        If the file is empty, lacks a required column, or has a malformed number.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     p = Path(d) / "log.csv"
    ...     _ = p.write_text("time;vm;used_mb\n0;a;100,5\n1;a;101\n", encoding="utf-8")
    ...     log = read_log(p)
    >>> log.vms["a"].used
    [100.5, 101.0]
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        if sep is None:
            try:
                sep = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
            except csv.Error:
                sep = ","
        reader = csv.reader(fh, delimiter=sep)
        try:
            header = [h.strip().lower() for h in next(reader)]
        except StopIteration:
            msg = f"{path.name}: the file is empty"
            raise ValueError(msg) from None
        col = {name: i for i, name in enumerate(header)}
        missing = [name for name in _REQUIRED if name not in col]
        if missing:
            msg = f"{path.name}: missing columns {', '.join(missing)}; found {', '.join(header)}"
            raise ValueError(msg)
        has_free = "free_mb" in col
        has_phase = "phase" in col
        raw: dict[str, list[tuple[float, float, float, bool]]] = {}
        for line_no, row in enumerate(reader, start=2):
            if not any(x.strip() for x in row):
                continue
            try:
                t = _number(row[col["time"]])
                used = _number(row[col["used_mb"]])
                free = _number(row[col["free_mb"]]) if has_free else math.nan
                vm = row[col["vm"]].strip()
                phase = row[col["phase"]].strip().lower() if has_phase else ""
            except (ValueError, IndexError) as exc:
                msg = f"{path.name}, line {line_no}: {exc}"
                raise ValueError(msg) from None
            raw.setdefault(vm, []).append((t, used, free, phase == GROWTH_PHASE))

    vms: dict[str, VmLog] = {}
    for name, rows in raw.items():
        rows.sort(key=lambda r: r[0])  # stable: the first of equal times is kept
        vm_log = VmLog(name)
        last_t = None
        for t, used, free, growth in rows:
            if last_t is not None and t == last_t:
                vm_log.duplicates += 1
                continue
            last_t = t
            vm_log.time.append(t)
            vm_log.used.append(used)
            vm_log.free.append(free)
            vm_log.growth.append(growth)
        vms[name] = vm_log
    return MonitoringLog(vms=vms, has_free=has_free, has_phase=has_phase)
