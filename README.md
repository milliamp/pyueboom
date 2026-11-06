# pyueboom

Async Python library to control **Ultimate Ears BOOM / MEGABOOM** speakers over Bluetooth LE:
power on, power off (standby), power state and battery level, read either by connecting or
passively from advertisements.

It's the protocol library behind the [UE BOOM Home Assistant integration](https://github.com/milliamp/ha-ueboom).

> Not affiliated with Logitech / Ultimate Ears. The protocol was reverse engineered from the
> official app by others (see [Credits](#credits)) and verified on a BOOM 3 (firmware 1.1.0.24).

## Install

```bash
pip install https://github.com/milliamp/pyueboom/releases/download/v0.1.0/pyueboom-0.1.0-py3-none-any.whl
```

## Usage

```python
import asyncio
from pyueboom import UEBoom


async def main():
    boom = UEBoom("C0:28:8D:00:11:22", host_mac="00:1A:7D:00:33:44")
    await boom.power_on()  # speaker wakes and connects for audio to host_mac
    state = await boom.update()
    print(state.is_on, state.battery_level, state.name, state.firmware_version)
    await boom.power_off()


asyncio.run(main())
```

CLI:

```bash
python -m pyueboom state C0:28:8D:00:11:22
python -m pyueboom on C0:28:8D:00:11:22 --host-mac 00:1A:7D:00:33:44
python -m pyueboom off C0:28:8D:00:11:22
```

Passive updates (e.g. from a `BleakScanner` or Home Assistant callback):

```python
boom.set_ble_device_and_advertisement_data(ble_device, advertisement_data)
boom.is_on, boom.battery_level  # decoded from manufacturer data, no connection needed
```

## Protocol

| What | How |
|---|---|
| Power | **Write Request** (not Write Command) to `c6d6dc0d-07f5-47ef-9b59-630622b01fd3`: 6-byte host MAC + `01` (on) / `02` (off). On power-on the speaker connects A2DP to that host, or to its last host if the MAC is all zeros. |
| State | Read `4356a21c-a599-4b94-a1c8-4b91fca02a9a`: `0x00` standby, `0x20` starting up (a few seconds after power-on), `0x40` on. |
| Battery | Standard Battery Level `0x2A19`. |
| Advertisement | Manufacturer data, company `0x0003`: byte 2 battery %, byte 4 power state, bytes 6–11 last host (standby) or zeros (on), bytes 12–17 speaker address. |

### Why there is a raw ATT transport

The speakers are dual-mode. You pair them over classic Bluetooth for audio, but they reject
LE bonding. BlueZ then always connects them over the classic bearer, so `bleak` on a local
BlueZ adapter fails with `br-connection-profile-unavailable`. On Linux with a local adapter,
pyueboom therefore opens the LE ATT channel directly with an L2CAP socket, the way `gatttool`
does. Everywhere else, such as ESPHome Bluetooth proxies, it uses `bleak` /
`bleak-retry-connector`. You can force a transport with `transport="raw"` or `transport="bleak"`.

The raw transport needs permission to open Bluetooth sockets. That's the default for root, and
for the Home Assistant container with host networking.

## Credits

- [kancelott/ue-boom-2-bt-le-reverse-engineering](https://github.com/kancelott/ue-boom-2-bt-le-reverse-engineering)
- [Shingyx/BoomSwitch](https://github.com/Shingyx/BoomSwitch) (state characteristic)
- [whayn/ueboom-ctl](https://github.com/whayn/ueboom-ctl), [alessandroaime/homebridge-ueboom](https://github.com/alessandroaime/homebridge-ueboom)

## License

MIT
