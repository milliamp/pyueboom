"""Classic-Bluetooth helpers via BlueZ over the system D-Bus (Linux only).

Power control is BLE (see :mod:`pyueboom.device`); audio is classic Bluetooth
(A2DP), handled by BlueZ on the host the speaker is paired with. These helpers
ask that host's BlueZ to (re)connect the speaker's audio, e.g. when it's on but
lost its connection after the audio server restarted.
"""

from __future__ import annotations

from .exceptions import UEBoomConnectionError, UEBoomError
from .models import normalize_mac

BLUEZ = "org.bluez"
DEVICE_IFACE = "org.bluez.Device1"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


def device_path(address: str, adapter: str = "hci0") -> str:
    """BlueZ object path for ``address`` on ``adapter``."""
    return f"/org/bluez/{adapter}/dev_{normalize_mac(address).replace(':', '_')}"


async def _call(path: str, interface: str, member: str, signature: str = "", body=None):
    try:
        from dbus_fast import BusType, Message, MessageType
        from dbus_fast.aio import MessageBus
    except ImportError as err:  # pragma: no cover - only on non-Linux installs
        raise UEBoomError("dbus-fast is required for BlueZ helpers") from err

    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    except (OSError, ValueError) as err:
        raise UEBoomConnectionError(f"Cannot reach the system D-Bus: {err}") from err
    try:
        reply = await bus.call(
            Message(
                destination=BLUEZ,
                path=path,
                interface=interface,
                member=member,
                signature=signature,
                body=body or [],
            )
        )
    finally:
        bus.disconnect()
    if reply.message_type == MessageType.ERROR:
        detail = reply.body[0] if reply.body else ""
        raise UEBoomConnectionError(f"BlueZ {member} failed: {reply.error_name} {detail}".strip())
    return reply.body


async def is_paired(address: str, adapter: str = "hci0") -> bool:
    """Return True if the host's BlueZ has the speaker paired."""
    try:
        (value,) = await _call(
            device_path(address, adapter), PROPS_IFACE, "Get", "ss", [DEVICE_IFACE, "Paired"]
        )
    except UEBoomConnectionError:
        return False
    return bool(value.value)


async def connect_audio(address: str, adapter: str = "hci0") -> None:
    """Ask BlueZ to connect the speaker's profiles (A2DP) to this host.

    The speaker must be on and paired with this host. For a dual-mode speaker
    bonded only over classic Bluetooth, BlueZ connects over classic, which is
    what audio needs.
    """
    await _call(device_path(address, adapter), DEVICE_IFACE, "Connect")
