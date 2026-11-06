from __future__ import annotations

from pyueboom.att import (
    parse_characteristic_declarations,
    parse_error_response,
    uuid_from_le_bytes,
)
from pyueboom.const import BATTERY_CHAR_UUID, POWER_CHAR_UUID


def test_uuid16() -> None:
    assert uuid_from_le_bytes(bytes.fromhex("192a")) == BATTERY_CHAR_UUID


def test_uuid128() -> None:
    raw = bytes.fromhex("c6d6dc0d07f547ef9b59630622b01fd3")[::-1]
    assert uuid_from_le_bytes(raw) == POWER_CHAR_UUID


def test_read_by_type_128() -> None:
    entry = bytes.fromhex("0200080300") + bytes.fromhex("c6d6dc0d07f547ef9b59630622b01fd3")[::-1]
    (char,) = parse_characteristic_declarations(bytes([0x09, len(entry)]) + entry)
    assert char.handle == 2
    assert char.value_handle == 3
    assert char.properties == 0x08
    assert char.uuid == POWER_CHAR_UUID


def test_read_by_type_16_multiple() -> None:
    entries = bytes.fromhex("1300021400192a") + bytes.fromhex("1500021600282a")
    chars = list(parse_characteristic_declarations(bytes([0x09, 7]) + entries))
    assert [c.value_handle for c in chars] == [0x14, 0x16]


def test_error_response() -> None:
    err = parse_error_response(bytes.fromhex("010801000a"))
    assert err.request_opcode == 0x08
    assert err.handle == 0x0001
    assert err.error_code == 0x0A
