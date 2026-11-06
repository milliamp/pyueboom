from __future__ import annotations

import pytest

from pyueboom import PowerCommand, UEBoomAdvertisement, UEBoomState
from pyueboom.models import build_power_payload, normalize_mac

# Captured from a BOOM 3 (firmware 1.1.0.24) on 2026-11-06.
ADV_ON = bytes.fromhex("011064004002000000000000c0288d00112228")
ADV_STANDBY = bytes.fromhex("011064000002001a7d003344c0288d00112228")


def test_normalize_mac() -> None:
    assert normalize_mac("c0288d001122") == "C0:28:8D:00:11:22"
    assert normalize_mac("c0-28-8d-00-11-22") == "C0:28:8D:00:11:22"
    with pytest.raises(ValueError):
        normalize_mac("nope")


def test_power_payload() -> None:
    assert build_power_payload("00:1A:7D:00:33:44", PowerCommand.ON).hex() == "001a7d00334401"
    assert build_power_payload("00:00:00:00:00:00", PowerCommand.OFF).hex() == "00000000000002"


def test_advertisement_on() -> None:
    adv = UEBoomAdvertisement.from_manufacturer_data({0x0003: ADV_ON})
    assert adv is not None
    assert adv.is_on
    assert adv.battery_level == 100
    assert adv.last_host is None
    assert adv.speaker_address == "C0:28:8D:00:11:22"


def test_advertisement_standby() -> None:
    adv = UEBoomAdvertisement.from_manufacturer_data({0x0003: ADV_STANDBY})
    assert adv is not None
    assert not adv.is_on
    assert adv.last_host == "00:1A:7D:00:33:44"


@pytest.mark.parametrize("data", [{}, {0x0003: b"\x01\x10"}, {0x004C: ADV_ON}])
def test_advertisement_ignored(data: dict[int, bytes]) -> None:
    assert UEBoomAdvertisement.from_manufacturer_data(data) is None


def test_state() -> None:
    state = UEBoomState(power_state=0x40, battery_level=55, firmware=bytes.fromhex("01010018"))
    assert state.is_on
    assert state.firmware_version == "1.1.0.24"
    assert not UEBoomState(power_state=0).is_on


@pytest.mark.parametrize(
    ("state", "on", "connected"),
    [(0x00, False, False), (0x20, True, False), (0x40, True, True), (0x60, True, True)],
)
def test_audio_connected_flag(state: int, on: bool, connected: bool) -> None:
    data = bytearray(ADV_ON)
    data[4] = state
    adv = UEBoomAdvertisement.from_manufacturer_data({0x0003: bytes(data)})
    assert adv is not None
    assert adv.is_on is on
    assert adv.audio_connected is connected
    assert UEBoomState(power_state=state).audio_connected is connected
