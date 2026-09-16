from __future__ import annotations

import pytest

from iras.safety_runtime import EmergencyStop


def test_emergency_stop_requires_local_clear(tmp_path):
    stop = EmergencyStop(tmp_path / "STOP")
    stop.assert_clear()
    stop.trip("test")
    with pytest.raises(PermissionError):
        stop.assert_clear()
    stop.clear()
    stop.assert_clear()
