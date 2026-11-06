"""Constants for the UE BOOM BLE protocol.

Reverse engineered from the Ultimate Ears app; see README for sources.
"""

from __future__ import annotations

from enum import IntEnum

#: Write Request with ``<6-byte host MAC><command>`` to switch power.
POWER_CHAR_UUID = "c6d6dc0d-07f5-47ef-9b59-630622b01fd3"
#: Single byte power state, see :class:`PowerState`.
STATE_CHAR_UUID = "4356a21c-a599-4b94-a1c8-4b91fca02a9a"
#: Standard GATT Battery Level (percent).
BATTERY_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
#: Standard GATT Device Name (the speaker's user-set name).
NAME_CHAR_UUID = "00002a00-0000-1000-8000-00805f9b34fb"
#: Standard GATT Firmware Revision (raw bytes, e.g. ``01 01 00 18``).
FIRMWARE_CHAR_UUID = "00002a28-0000-1000-8000-00805f9b34fb"
#: Standard GATT Serial Number String.
SERIAL_CHAR_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
#: Ultimate Ears color code.
COLOR_CHAR_UUID = "54f7f292-7ebb-4267-83c2-8e6ee7e881ff"

#: Bluetooth SIG company identifier used in UE BOOM manufacturer data.
MANUFACTURER_ID = 0x0003

#: Host MAC used when none is given; the speaker then reconnects to its last host.
ZERO_MAC = "00:00:00:00:00:00"


class PowerCommand(IntEnum):
    """Last byte of the power characteristic payload."""

    ON = 0x01
    OFF = 0x02


class PowerState(IntEnum):
    """Values seen in the state characteristic and advertisement byte 4."""

    STANDBY = 0x00
    #: Seen for a few seconds right after a power-on command.
    STARTING = 0x20
    ON = 0x40
