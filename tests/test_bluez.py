from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from pyueboom import UEBoomConnectionError, bluez


def test_device_path() -> None:
    assert bluez.device_path("c0:28:8d:00:11:22") == "/org/bluez/hci0/dev_C0_28_8D_00_11_22"
    assert bluez.device_path("C0:28:8D:00:11:22", "hci1").startswith("/org/bluez/hci1/")


async def test_connect_audio_calls_device_connect() -> None:
    with patch("pyueboom.bluez._call", AsyncMock(return_value=[])) as call:
        await bluez.connect_audio("C0:28:8D:00:11:22")
    call.assert_awaited_once_with(
        "/org/bluez/hci0/dev_C0_28_8D_00_11_22", "org.bluez.Device1", "Connect"
    )


async def test_is_paired() -> None:
    with patch("pyueboom.bluez._call", AsyncMock(return_value=[SimpleNamespace(value=True)])):
        assert await bluez.is_paired("C0:28:8D:00:11:22")
    with patch("pyueboom.bluez._call", AsyncMock(side_effect=UEBoomConnectionError("x"))):
        assert not await bluez.is_paired("C0:28:8D:00:11:22")


async def test_connect_audio_error_propagates() -> None:
    with (
        patch("pyueboom.bluez._call", AsyncMock(side_effect=UEBoomConnectionError("down"))),
        pytest.raises(UEBoomConnectionError),
    ):
        await bluez.connect_audio("C0:28:8D:00:11:22")
