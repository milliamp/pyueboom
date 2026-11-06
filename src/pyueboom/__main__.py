"""Command line: ``python -m pyueboom {on,off,state} ADDRESS [--host-mac MAC]``."""

from __future__ import annotations

import argparse
import asyncio
import logging

from .device import UEBoom


async def _main(args: argparse.Namespace) -> None:
    boom = UEBoom(
        args.address,
        host_mac=args.host_mac,
        adapter_address=args.adapter,
        transport=args.transport,
    )
    if args.command == "on":
        await boom.power_on()
    elif args.command == "off":
        await boom.power_off()
    state = await boom.update()
    print(
        f"{state.name or boom.address}: {'on' if state.is_on else 'standby'} "
        f"(0x{state.power_state:02x}), battery {state.battery_level}%, "
        f"firmware {state.firmware_version}, serial {state.serial_number}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="pyueboom", description=__doc__)
    parser.add_argument("command", choices=["on", "off", "state"])
    parser.add_argument("address", help="speaker Bluetooth address")
    parser.add_argument("--host-mac", help="host to connect audio to (default: last host)")
    parser.add_argument("--adapter", help="local adapter address to connect from")
    parser.add_argument("--transport", choices=["auto", "raw", "bleak"], default="auto")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
