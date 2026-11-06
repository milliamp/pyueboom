from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pyueboom import UEBoom, UEBoomConnectionError
from pyueboom.const import (
    BATTERY_CHAR_UUID,
    FIRMWARE_CHAR_UUID,
    NAME_CHAR_UUID,
    POWER_CHAR_UUID,
    SERIAL_CHAR_UUID,
    STATE_CHAR_UUID,
)
from pyueboom.exceptions import CharacteristicMissingError
from pyueboom.transport import choose_mode

ADDR = "C0:28:8D:00:11:22"


class FakeConn:
    def __init__(self, values: dict[str, bytes], fail: int = 0) -> None:
        self.values = values
        self.writes: list[tuple[str, bytes]] = []
        self.fail = fail

    async def read(self, uuid: str) -> bytes:
        if uuid not in self.values:
            raise CharacteristicMissingError(uuid)
        return self.values[uuid]

    async def write(self, uuid: str, data: bytes) -> None:
        self.writes.append((uuid, data))


def fake_open(conn: FakeConn):
    calls = {"n": 0}

    @asynccontextmanager
    async def _open(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= conn.fail:
            raise UEBoomConnectionError("boom")
        yield conn

    return _open, calls


VALUES = {
    STATE_CHAR_UUID: b"\x40",
    BATTERY_CHAR_UUID: b"\x5d",
    NAME_CHAR_UUID: b"My BOOM\x00",
    SERIAL_CHAR_UUID: b"0000AB000XY0\x00",
    FIRMWARE_CHAR_UUID: bytes.fromhex("01010018"),
}


async def test_update() -> None:
    conn = FakeConn(VALUES)
    opener, _ = fake_open(conn)
    boom = UEBoom(ADDR)
    fired = []
    boom.register_callback(lambda: fired.append(1))
    with patch("pyueboom.device.open_connection", opener):
        state = await boom.update()
    assert state.is_on
    assert state.battery_level == 93
    assert state.name == "My BOOM"
    assert state.serial_number == "0000AB000XY0"
    assert boom.is_on is True
    assert fired == [1]


async def test_update_optional_chars_missing() -> None:
    conn = FakeConn({STATE_CHAR_UUID: b"\x00"})
    opener, _ = fake_open(conn)
    with patch("pyueboom.device.open_connection", opener):
        state = await UEBoom(ADDR).update()
    assert not state.is_on
    assert state.battery_level is None


async def test_power_on_uses_host_mac() -> None:
    conn = FakeConn(VALUES)
    opener, _ = fake_open(conn)
    boom = UEBoom(ADDR, host_mac="00:1a:7d:00:33:44")
    with patch("pyueboom.device.open_connection", opener):
        await boom.power_on()
        await boom.power_off()
    assert conn.writes == [
        (POWER_CHAR_UUID, bytes.fromhex("001a7d00334401")),
        (POWER_CHAR_UUID, bytes.fromhex("001a7d00334402")),
    ]


async def test_retries_then_succeeds() -> None:
    conn = FakeConn(VALUES, fail=2)
    opener, calls = fake_open(conn)
    with patch("pyueboom.device.open_connection", opener), patch("asyncio.sleep"):
        await UEBoom(ADDR).power_on()
    assert calls["n"] == 3


async def test_retries_exhausted() -> None:
    conn = FakeConn(VALUES, fail=99)
    opener, _ = fake_open(conn)
    with (
        patch("pyueboom.device.open_connection", opener),
        patch("asyncio.sleep"),
        pytest.raises(UEBoomConnectionError),
    ):
        await UEBoom(ADDR).power_on()


def test_advertisement_callback() -> None:
    boom = UEBoom(ADDR)
    fired = []
    boom.register_callback(lambda: fired.append(1))
    device = SimpleNamespace(address=ADDR, details={})
    on = SimpleNamespace(
        manufacturer_data={3: bytes.fromhex("011064004002000000000000c0288d00112228")}
    )
    boom.set_ble_device_and_advertisement_data(device, on)
    boom.set_ble_device_and_advertisement_data(device, on)  # unchanged -> no callback
    assert boom.is_on is True
    assert boom.battery_level == 100
    assert fired == [1]


def test_choose_mode() -> None:
    bluez = SimpleNamespace(details={"path": "/org/bluez/hci0/dev_C0_28_8D_00_11_22"})
    proxy = SimpleNamespace(details={"source": "AA:BB:CC:DD:EE:FF", "address_type": 0})
    assert choose_mode("bleak", bluez) == "bleak"
    assert choose_mode("raw", proxy) == "raw"
    assert choose_mode("auto", proxy) == "bleak"
    with patch("pyueboom.transport.att.is_supported", return_value=True):
        assert choose_mode("auto", bluez) == "raw"
    with patch("pyueboom.transport.att.is_supported", return_value=False):
        assert choose_mode("auto", bluez) == "bleak"
