"""Control Ultimate Ears BOOM speakers over Bluetooth LE."""

from __future__ import annotations

from .const import MANUFACTURER_ID, PowerCommand, PowerState
from .device import UEBoom
from .exceptions import (
    AttError,
    CharacteristicMissingError,
    UEBoomConnectionError,
    UEBoomError,
)
from .models import UEBoomAdvertisement, UEBoomState

__version__ = "0.1.0"

__all__ = [
    "MANUFACTURER_ID",
    "AttError",
    "CharacteristicMissingError",
    "PowerCommand",
    "PowerState",
    "UEBoom",
    "UEBoomAdvertisement",
    "UEBoomConnectionError",
    "UEBoomError",
    "UEBoomState",
    "__version__",
]
