"""Connections to the speaker: raw ATT on local BlueZ adapters, bleak elsewhere."""

from __future__ import annotations

import logging
import re
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Literal, Protocol

from . import att
from .exceptions import CharacteristicMissingError, UEBoomConnectionError

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

TransportMode = Literal["auto", "raw", "bleak"]

_BLUEZ_PATH = re.compile(r"^/org/bluez/(hci\d+)/dev_")


class Connection(Protocol):
    """An open GATT connection."""

    async def read(self, char_uuid: str) -> bytes: ...

    async def write(self, char_uuid: str, data: bytes) -> None: ...


def bluez_adapter(ble_device: BLEDevice | None) -> str | None:
    """Return ``hciN`` if ``ble_device`` was seen by a local BlueZ adapter."""
    if ble_device is None or not isinstance(ble_device.details, dict):
        return None
    match = _BLUEZ_PATH.match(str(ble_device.details.get("path", "")))
    return match.group(1) if match else None


def _is_random(ble_device: BLEDevice | None) -> bool:
    if ble_device is None or not isinstance(ble_device.details, dict):
        return False
    props = ble_device.details.get("props") or {}
    return (
        str(props.get("AddressType") or ble_device.details.get("address_type", "")).lower()
        == "random"
    )


def choose_mode(mode: TransportMode, ble_device: BLEDevice | None) -> Literal["raw", "bleak"]:
    """Resolve ``auto``: raw ATT for local BlueZ adapters (or no BLEDevice), bleak otherwise."""
    if mode != "auto":
        return mode
    if att.is_supported() and (ble_device is None or bluez_adapter(ble_device)):
        return "raw"
    return "bleak"


class _RawConnection(AbstractAsyncContextManager["_RawConnection"]):
    def __init__(
        self, address: str, adapter_address: str | None, random: bool, timeout: float
    ) -> None:
        self._client = att.AttClient(
            address, adapter_address=adapter_address, random_address=random, timeout=timeout
        )

    async def __aenter__(self) -> _RawConnection:
        await self._client.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._client.close()

    async def read(self, char_uuid: str) -> bytes:
        return await self._client.read(char_uuid)

    async def write(self, char_uuid: str, data: bytes) -> None:
        await self._client.write(char_uuid, data)


class _BleakConnection(AbstractAsyncContextManager["_BleakConnection"]):
    def __init__(self, ble_device: BLEDevice, timeout: float) -> None:
        self._ble_device = ble_device
        self._timeout = timeout
        self._client = None

    async def __aenter__(self) -> _BleakConnection:
        from bleak.exc import BleakError
        from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

        try:
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._ble_device.name or self._ble_device.address,
                max_attempts=3,
            )
        except (BleakError, TimeoutError) as ex:
            raise UEBoomConnectionError(f"BLE connect failed: {ex}") from ex
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.disconnect()

    def _char(self, char_uuid: str):
        assert self._client is not None
        char = self._client.services.get_characteristic(char_uuid)
        if char is None:
            raise CharacteristicMissingError(char_uuid)
        return char

    async def read(self, char_uuid: str) -> bytes:
        from bleak.exc import BleakError

        try:
            return bytes(await self._client.read_gatt_char(self._char(char_uuid)))
        except BleakError as ex:
            raise UEBoomConnectionError(str(ex)) from ex

    async def write(self, char_uuid: str, data: bytes) -> None:
        from bleak.exc import BleakError

        try:
            await self._client.write_gatt_char(self._char(char_uuid), data, response=True)
        except BleakError as ex:
            raise UEBoomConnectionError(str(ex)) from ex


def open_connection(
    address: str,
    ble_device: BLEDevice | None,
    *,
    mode: TransportMode = "auto",
    adapter_address: str | None = None,
    timeout: float = 10.0,
) -> AbstractAsyncContextManager[Connection]:
    """Return an async context manager yielding an open :class:`Connection`."""
    resolved = choose_mode(mode, ble_device)
    _LOGGER.debug("Connecting to %s using %s transport", address, resolved)
    if resolved == "raw":
        return _RawConnection(address, adapter_address, _is_random(ble_device), timeout)
    if ble_device is None:
        raise ValueError("The bleak transport needs a BLEDevice")
    return _BleakConnection(ble_device, timeout)
