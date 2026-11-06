"""Data models for UE BOOM speakers.

The models mirror what the speaker reports and do not interpret it further.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import AUDIO_CONNECTED_FLAG, MANUFACTURER_ID, PowerCommand, PowerState


def normalize_mac(mac: str) -> str:
    """Return ``mac`` as upper-case ``AA:BB:CC:DD:EE:FF``.

    Raises ValueError for anything that isn't 6 hex bytes.
    """
    digits = mac.replace(":", "").replace("-", "").strip().upper()
    if len(digits) != 12 or any(c not in "0123456789ABCDEF" for c in digits):
        raise ValueError(f"Invalid Bluetooth address: {mac!r}")
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def build_power_payload(host_mac: str, command: PowerCommand) -> bytes:
    """Return the 7-byte power characteristic payload."""
    return bytes.fromhex(normalize_mac(host_mac).replace(":", "")) + bytes([command])


def _mac_from_bytes(data: bytes) -> str:
    return ":".join(f"{b:02X}" for b in data)


@dataclass(frozen=True, slots=True)
class UEBoomAdvertisement:
    """Fields decoded from the manufacturer data (company 0x0003).

    Layout seen on a BOOM 3 (19 bytes)::

        01 10 64 00 40 02 000000000000 C0288D001122 28
              ^^    ^^    ^^^^^^^^^^^^ ^^^^^^^^^^^^
              |     |     |            speaker address
              |     |     last host while in standby, zeros while on
              |     power state (see PowerState)
              battery percent
    """

    raw: bytes
    battery_level: int
    power_state: int
    last_host: str | None
    speaker_address: str

    @property
    def is_on(self) -> bool:
        """Return True if the speaker reports it is on."""
        return self.power_state != PowerState.STANDBY

    @property
    def audio_connected(self) -> bool:
        """Return True if the speaker has an audio (A2DP) connection."""
        return bool(self.power_state & AUDIO_CONNECTED_FLAG)

    @classmethod
    def from_manufacturer_data(
        cls, manufacturer_data: dict[int, bytes]
    ) -> UEBoomAdvertisement | None:
        """Parse a bleak/HA ``manufacturer_data`` mapping, or return None."""
        data = manufacturer_data.get(MANUFACTURER_ID)
        if data is None or len(data) < 18:
            return None
        last_host = data[6:12]
        return cls(
            raw=bytes(data),
            battery_level=data[2],
            power_state=data[4],
            last_host=None if not any(last_host) else _mac_from_bytes(last_host),
            speaker_address=_mac_from_bytes(data[12:18]),
        )


@dataclass(frozen=True, slots=True)
class UEBoomState:
    """State read from the speaker over GATT."""

    power_state: int
    battery_level: int | None = None
    name: str | None = None
    serial_number: str | None = None
    firmware: bytes | None = None

    @property
    def is_on(self) -> bool:
        """Return True if the speaker reports it is on."""
        return self.power_state != PowerState.STANDBY

    @property
    def audio_connected(self) -> bool:
        """Return True if the speaker has an audio (A2DP) connection."""
        return bool(self.power_state & AUDIO_CONNECTED_FLAG)

    @property
    def firmware_version(self) -> str | None:
        """Firmware bytes joined with dots, as reported (e.g. ``1.1.0.24``)."""
        if self.firmware is None:
            return None
        return ".".join(str(b) for b in self.firmware)
