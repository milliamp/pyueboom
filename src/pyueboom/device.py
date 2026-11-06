"""High-level UE BOOM speaker API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from .const import (
    BATTERY_CHAR_UUID,
    FIRMWARE_CHAR_UUID,
    NAME_CHAR_UUID,
    POWER_CHAR_UUID,
    SERIAL_CHAR_UUID,
    STATE_CHAR_UUID,
    ZERO_MAC,
    PowerCommand,
)
from .exceptions import CharacteristicMissingError, UEBoomConnectionError
from .models import UEBoomAdvertisement, UEBoomState, build_power_payload, normalize_mac
from .transport import Connection, TransportMode, open_connection

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData

_LOGGER = logging.getLogger(__name__)

#: Connection attempts per operation. The speaker sometimes drops the first LE
#: connection right after a power change.
ATTEMPTS = 3


def _decode_str(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


class UEBoom:
    """A UE BOOM / MEGABOOM speaker reachable over Bluetooth LE.

    ``host_mac`` goes into power commands. The speaker connects for audio to the
    host with that address, or to its last host if it is all zeros (the default).
    """

    def __init__(
        self,
        address_or_device: str | BLEDevice,
        *,
        host_mac: str | None = None,
        adapter_address: str | None = None,
        transport: TransportMode = "auto",
        timeout: float = 10.0,
    ) -> None:
        if isinstance(address_or_device, str):
            self._address = normalize_mac(address_or_device)
            self._ble_device: BLEDevice | None = None
        else:
            self._address = normalize_mac(address_or_device.address)
            self._ble_device = address_or_device
        self.host_mac = normalize_mac(host_mac) if host_mac else ZERO_MAC
        self.adapter_address = normalize_mac(adapter_address) if adapter_address else None
        self.transport: TransportMode = transport
        self.timeout = timeout
        self._advertisement: UEBoomAdvertisement | None = None
        self._state: UEBoomState | None = None
        self._callbacks: list[Callable[[], None]] = []
        self._op_lock = asyncio.Lock()

    @property
    def address(self) -> str:
        """Bluetooth address of the speaker."""
        return self._address

    @property
    def advertisement(self) -> UEBoomAdvertisement | None:
        """Most recent decoded advertisement, if any."""
        return self._advertisement

    @property
    def state(self) -> UEBoomState | None:
        """Most recent state read over GATT, if any."""
        return self._state

    @property
    def is_on(self) -> bool | None:
        """Power state from the newest source (advertisement or GATT read)."""
        if self._advertisement is not None:
            return self._advertisement.is_on
        if self._state is not None:
            return self._state.is_on
        return None

    @property
    def battery_level(self) -> int | None:
        """Battery percent from the newest source."""
        if self._advertisement is not None:
            return self._advertisement.battery_level
        if self._state is not None:
            return self._state.battery_level
        return None

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Call ``callback`` whenever the state changes; returns an unsubscribe function."""
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback)

    def _fire(self) -> None:
        for callback in list(self._callbacks):
            callback()

    def set_ble_device_and_advertisement_data(
        self, ble_device: BLEDevice, advertisement_data: AdvertisementData
    ) -> None:
        """Feed a new advertisement (e.g. from a scanner callback)."""
        self._ble_device = ble_device
        adv = UEBoomAdvertisement.from_manufacturer_data(advertisement_data.manufacturer_data)
        if adv is not None and adv != self._advertisement:
            self._advertisement = adv
            self._fire()

    async def _run[T](self, op: Callable[[Connection], Awaitable[T]]) -> T:
        last: Exception | None = None
        async with self._op_lock:
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    async with open_connection(
                        self._address,
                        self._ble_device,
                        mode=self.transport,
                        adapter_address=self.adapter_address,
                        timeout=self.timeout,
                    ) as conn:
                        return await op(conn)
                except UEBoomConnectionError as ex:
                    last = ex
                    _LOGGER.debug("%s: attempt %s failed: %s", self._address, attempt, ex)
                    await asyncio.sleep(0.5 * attempt)
        assert last is not None
        raise last

    async def update(self) -> UEBoomState:
        """Connect and read power state, battery and device information."""

        async def op(conn: Connection) -> UEBoomState:
            power = (await conn.read(STATE_CHAR_UUID))[0]
            extra: dict[str, object] = {}
            for key, uuid, conv in (
                ("battery_level", BATTERY_CHAR_UUID, lambda b: b[0]),
                ("name", NAME_CHAR_UUID, _decode_str),
                ("serial_number", SERIAL_CHAR_UUID, _decode_str),
                ("firmware", FIRMWARE_CHAR_UUID, bytes),
            ):
                with contextlib.suppress(CharacteristicMissingError):
                    extra[key] = conv(await conn.read(uuid))
            return UEBoomState(power_state=power, **extra)  # type: ignore[arg-type]

        self._state = await self._run(op)
        self._fire()
        return self._state

    async def _power(self, command: PowerCommand) -> None:
        payload = build_power_payload(self.host_mac, command)

        async def op(conn: Connection) -> None:
            await conn.write(POWER_CHAR_UUID, payload)

        _LOGGER.debug("%s: power %s", self._address, command.name)
        await self._run(op)

    async def power_on(self) -> None:
        """Wake the speaker from standby."""
        await self._power(PowerCommand.ON)

    async def power_off(self) -> None:
        """Put the speaker into standby."""
        await self._power(PowerCommand.OFF)
