"""Exceptions raised by pyueboom."""

from __future__ import annotations


class UEBoomError(Exception):
    """Base class for all pyueboom errors."""


class UEBoomConnectionError(UEBoomError):
    """The speaker could not be reached over Bluetooth LE."""


class CharacteristicMissingError(UEBoomError):
    """The speaker does not expose a required GATT characteristic."""


class AttError(UEBoomError):
    """The speaker answered an ATT request with an error response."""

    def __init__(self, request_opcode: int, handle: int, error_code: int) -> None:
        super().__init__(
            f"ATT error 0x{error_code:02x} for request 0x{request_opcode:02x} "
            f"on handle 0x{handle:04x}"
        )
        self.request_opcode = request_opcode
        self.handle = handle
        self.error_code = error_code
