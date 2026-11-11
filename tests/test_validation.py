"""validate_measurement: types, values and time order of a reading, and its use in monitors."""

import math
from fractions import Fraction

import numpy as np
import pytest

from azarovo_martingale import FleetMonitor, VmMonitor, validate_measurement


@pytest.mark.parametrize(
    "value",
    [True, False, "1.0", None, 1 + 2j, [1.0], b"1"],
    ids=["true", "false", "str", "none", "complex", "list", "bytes"],
)
@pytest.mark.parametrize("position", ["t", "used", "free"])
def test_non_real_values_raise_type_error(value, position):
    args = {"t": 1.0, "used": 2048.0, "free": 1352.0}
    args[position] = value
    with pytest.raises(TypeError, match=position):
        validate_measurement(args["t"], args["used"], args["free"])


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("position", ["t", "used", "free"])
def test_non_finite_values_raise_value_error(bad, position):
    args = {"t": 1.0, "used": 2048.0, "free": 1352.0}
    args[position] = bad
    with pytest.raises(ValueError, match="finite"):
        validate_measurement(args["t"], args["used"], args["free"])


@pytest.mark.parametrize(
    ("t", "used", "free", "label"),
    [(-1.0, 1.0, 1.0, "t"), (0.0, -1.0, 1.0, "used"), (0.0, 1.0, -0.5, "free")],
)
def test_negative_values_raise_value_error(t, used, free, label):
    with pytest.raises(ValueError, match=f"{label} must be non-negative"):
        validate_measurement(t, used, free)


def test_time_must_increase_when_previous_time_is_given():
    assert validate_measurement(5.0, 1.0, 1.0, last_t=4.0) == (5.0, 1.0, 1.0)
    with pytest.raises(ValueError, match="must increase"):
        validate_measurement(4.0, 1.0, 1.0, last_t=4.0)
    with pytest.raises(ValueError, match="must increase"):
        validate_measurement(3.0, 1.0, 1.0, last_t=4.0)


def test_first_reading_needs_no_previous_time():
    assert validate_measurement(0.0, 0.0, 0.0) == (0.0, 0.0, 0.0)


def test_valid_numbers_are_returned_as_floats():
    out = validate_measurement(np.int64(3), np.float32(2048), Fraction(1, 2))
    assert out == (3.0, 2048.0, 0.5)
    assert all(type(x) is float for x in out)


def test_monitor_refuses_bad_reading_without_changing_state():
    vm = VmMonitor("vm", c=20.0)
    vm.record_measurement(0.0, used=2048.0, free=1352.0)
    before = vm.to_dict()
    with pytest.raises(TypeError):
        vm.record_measurement(1.0, used=True, free=1352.0)
    with pytest.raises(ValueError):
        vm.record_measurement(0.0, used=2048.0, free=1352.0)
    with pytest.raises(ValueError):
        vm.record_measurement(2.0, used=math.nan, free=1352.0)
    assert vm.to_dict() == before


def test_fleet_refuses_bad_reading_and_registers_nothing():
    fleet = FleetMonitor(n_vms=2, c=20.0)
    with pytest.raises(TypeError):
        fleet.record_measurement("vm-x", None, used=1.0, free=1.0)
    with pytest.raises(ValueError):
        fleet.record_measurement("vm-y", 1.0, used=-1.0, free=1.0)
    assert len(fleet) == 0


def test_old_streaming_name_is_gone():
    assert not hasattr(VmMonitor, "update")
    assert not hasattr(FleetMonitor, "update")
