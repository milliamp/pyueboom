"""A minimal asyncio ATT client over a raw Linux L2CAP LE socket.

Why this exists: UE BOOM speakers are dual-mode (classic + LE) devices that are
paired over classic Bluetooth for audio but refuse LE bonding. BlueZ (at least
up to 5.7x) then always picks the classic bearer for ``Device1.Connect``, so
bleak on a local BlueZ adapter fails with ``br-connection-profile-unavailable``.
Opening the LE ATT fixed channel directly, as ``gatttool`` does, side-steps the
bearer selection. Only the handful of ATT operations this library needs are
implemented.
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import errno
import socket
import struct
import sys
import uuid as uuid_mod
from collections.abc import Iterator
from dataclasses import dataclass

from .exceptions import AttError, CharacteristicMissingError, UEBoomConnectionError

ATT_CID = 4
BDADDR_LE_PUBLIC = 1
BDADDR_LE_RANDOM = 2

OP_ERROR_RSP = 0x01
OP_READ_BY_TYPE_REQ = 0x08
OP_READ_BY_TYPE_RSP = 0x09
OP_READ_REQ = 0x0A
OP_READ_RSP = 0x0B
OP_WRITE_REQ = 0x12
OP_WRITE_RSP = 0x13
OP_HANDLE_VALUE_NTF = 0x1B
OP_HANDLE_VALUE_IND = 0x1D
OP_HANDLE_VALUE_CFM = 0x1E

ERR_ATTRIBUTE_NOT_FOUND = 0x0A
CHARACTERISTIC_DECLARATION = 0x2803


def is_supported() -> bool:
    """Return True if raw Bluetooth sockets can be used on this platform."""
    return sys.platform.startswith("linux") and hasattr(socket, "AF_BLUETOOTH")


@dataclass(frozen=True, slots=True)
class Characteristic:
    """A characteristic declaration found during discovery."""

    handle: int
    properties: int
    value_handle: int
    uuid: str


def uuid_from_le_bytes(data: bytes) -> str:
    """Convert a 16- or 128-bit little-endian ATT UUID to its string form."""
    if len(data) == 2:
        return f"0000{struct.unpack('<H', data)[0]:04x}-0000-1000-8000-00805f9b34fb"
    if len(data) == 16:
        return str(uuid_mod.UUID(bytes=data[::-1]))
    raise ValueError(f"Bad UUID length {len(data)}")


def parse_error_response(pdu: bytes) -> AttError:
    """Decode an ATT Error Response PDU."""
    opcode, handle, code = struct.unpack("<BHB", pdu[1:5])
    return AttError(opcode, handle, code)


def parse_characteristic_declarations(pdu: bytes) -> Iterator[Characteristic]:
    """Decode a Read By Type Response holding characteristic declarations."""
    length = pdu[1]
    for i in range(2, len(pdu) - length + 1, length):
        entry = pdu[i : i + length]
        handle, props, value_handle = struct.unpack("<HBH", entry[:5])
        yield Characteristic(handle, props, value_handle, uuid_from_le_bytes(entry[5:]))


class _SockaddrL2(ctypes.Structure):
    _fields_ = [
        ("l2_family", ctypes.c_ushort),
        ("l2_psm", ctypes.c_ushort),
        ("l2_bdaddr", ctypes.c_ubyte * 6),
        ("l2_cid", ctypes.c_ushort),
        ("l2_bdaddr_type", ctypes.c_ubyte),
    ]


def _sockaddr(mac: str, addr_type: int) -> _SockaddrL2:
    addr = _SockaddrL2()
    addr.l2_family = socket.AF_BLUETOOTH
    addr.l2_bdaddr = (ctypes.c_ubyte * 6)(*bytes.fromhex(mac.replace(":", ""))[::-1])
    addr.l2_cid = ATT_CID
    addr.l2_bdaddr_type = addr_type
    return addr


_libc: ctypes.CDLL | None = None


def _get_libc() -> ctypes.CDLL:
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)
    return _libc


class AttClient:
    """Connect to a peripheral's LE ATT channel and issue simple requests."""

    def __init__(
        self,
        address: str,
        *,
        adapter_address: str | None = None,
        random_address: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self.address = address
        self.adapter_address = adapter_address
        self.addr_type = BDADDR_LE_RANDOM if random_address else BDADDR_LE_PUBLIC
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._lock = asyncio.Lock()
        self._chars: dict[str, Characteristic] | None = None

    async def __aenter__(self) -> AttClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.close()

    async def connect(self) -> None:
        """Open the ATT channel."""
        if not is_supported():
            raise UEBoomConnectionError("Raw Bluetooth sockets need Linux")
        libc = _get_libc()
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        try:
            sock.setblocking(False)
            local = _sockaddr(self.adapter_address or "00:00:00:00:00:00", BDADDR_LE_PUBLIC)
            if libc.bind(sock.fileno(), ctypes.byref(local), ctypes.sizeof(local)) != 0:
                err = ctypes.get_errno()
                raise OSError(err, f"bind: {errno.errorcode.get(err, err)}")
            remote = _sockaddr(self.address, self.addr_type)
            if libc.connect(sock.fileno(), ctypes.byref(remote), ctypes.sizeof(remote)) != 0:
                err = ctypes.get_errno()
                if err != errno.EINPROGRESS:
                    raise OSError(err, f"connect: {errno.errorcode.get(err, err)}")
                await self._wait_writable(sock)
                err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if err:
                    raise OSError(err, f"connect: {errno.errorcode.get(err, err)}")
        except (OSError, TimeoutError) as ex:
            sock.close()
            raise UEBoomConnectionError(f"LE connect to {self.address} failed: {ex}") from ex
        self._sock = sock

    async def _wait_writable(self, sock: socket.socket) -> None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        loop.add_writer(sock.fileno(), lambda: fut.done() or fut.set_result(None))
        try:
            async with asyncio.timeout(self.timeout):
                await fut
        finally:
            loop.remove_writer(sock.fileno())

    def close(self) -> None:
        """Close the ATT channel."""
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    async def request(self, pdu: bytes) -> bytes:
        """Send a request PDU and return the response PDU."""
        if self._sock is None:
            raise UEBoomConnectionError("Not connected")
        loop = asyncio.get_running_loop()
        async with self._lock:
            try:
                async with asyncio.timeout(self.timeout):
                    await loop.sock_sendall(self._sock, pdu)
                    while True:
                        rsp = await loop.sock_recv(self._sock, 517)
                        if not rsp:
                            raise UEBoomConnectionError("Connection closed")
                        if rsp[0] == OP_HANDLE_VALUE_IND:
                            await loop.sock_sendall(self._sock, bytes([OP_HANDLE_VALUE_CFM]))
                            continue
                        if rsp[0] == OP_HANDLE_VALUE_NTF:
                            continue
                        break
            except (OSError, TimeoutError) as ex:
                self.close()
                raise UEBoomConnectionError(f"ATT request failed: {ex}") from ex
        if rsp[0] == OP_ERROR_RSP:
            raise parse_error_response(rsp)
        return rsp

    async def characteristics(self) -> dict[str, Characteristic]:
        """Discover all characteristic declarations, keyed by UUID."""
        if self._chars is not None:
            return self._chars
        found: dict[str, Characteristic] = {}
        start = 0x0001
        while start <= 0xFFFF:
            pdu = struct.pack(
                "<BHHH", OP_READ_BY_TYPE_REQ, start, 0xFFFF, CHARACTERISTIC_DECLARATION
            )
            try:
                rsp = await self.request(pdu)
            except AttError as ex:
                if ex.error_code == ERR_ATTRIBUTE_NOT_FOUND:
                    break
                raise
            last = start
            for char in parse_characteristic_declarations(rsp):
                found.setdefault(char.uuid, char)
                last = char.handle
            if last < start:
                break
            start = last + 1
        self._chars = found
        return found

    async def _value_handle(self, char_uuid: str) -> int:
        chars = await self.characteristics()
        try:
            return chars[char_uuid.lower()].value_handle
        except KeyError:
            raise CharacteristicMissingError(char_uuid) from None

    async def read(self, char_uuid: str) -> bytes:
        """Read a characteristic value (first MTU-1 bytes)."""
        handle = await self._value_handle(char_uuid)
        rsp = await self.request(struct.pack("<BH", OP_READ_REQ, handle))
        return rsp[1:]

    async def write(self, char_uuid: str, data: bytes) -> None:
        """Write a characteristic value with a Write Request."""
        handle = await self._value_handle(char_uuid)
        await self.request(struct.pack("<BH", OP_WRITE_REQ, handle) + data)
