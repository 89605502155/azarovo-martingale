"""Saving the state of a monitor to JSON and restoring it after a restart."""

import json
import tempfile
from pathlib import Path

from azarovo_martingale import VmMonitor

vm = VmMonitor("vm-1", c=20.0, delta=0.01)
for t, used in ((0.0, 2048.0), (1.0, 2049.0), (2.0, 2046.0)):
    vm.record_measurement(t, used, free=1352.0)

with tempfile.TemporaryDirectory() as folder:
    state = Path(folder) / "vm-1.json"
    state.write_text(json.dumps(vm.to_dict(), indent=2), encoding="utf-8")
    restored = VmMonitor.from_dict(json.loads(state.read_text(encoding="utf-8")))

same = restored.record_measurement(3.0, 2050.0, 1350.0) == vm.record_measurement(
    3.0, 2050.0, 1350.0
)
print("restored monitor takes the same decisions:", same)
print("next check at t =", restored.next_check_time)
