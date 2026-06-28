# Livebox TV UHD — HomeKit bridge

A small **standalone** HomeKit accessory that exposes the Orange Livebox TV UHD
set-top box to Apple Home — **without Home Assistant**. It pairs directly with
the Home app and appears as a **TV Set-Top Box** accessory: power, channel
inputs, volume and the Control-Center remote all work natively.

It reuses the exact same local HTTP control protocol as the Home Assistant
integration (`http://<box>:8080/remoteControl/cmd`), and loads its channel
lists from the integration's `const_<country>.py` files so the two never drift
apart.

```
Apple Home  ⇄  HAP-python bridge (this app)  ⇄  Livebox TV UHD (local HTTP)
```

## What you get in HomeKit

| HomeKit control            | Livebox action                          |
|----------------------------|------------------------------------------|
| Power on / off             | `POWER` key (wakes from / puts to standby) |
| Input selection            | Tune to the selected channel             |
| Volume up / down (remote)  | `VOL+` / `VOL-`                          |
| Mute                       | `MUTE`                                    |
| Apple TV Remote (Control Center) directional pad, select, back, menu, play/pause, rewind, fast-forward, info | Mapped to the box's remote keys |
| Channel up / down          | Next / previous track on the remote       |

The accessory also polls the box (every 10 s by default) so Home reflects the
real power state and current channel.

## Requirements

- Python 3.10+
- A host on the **same LAN/subnet** as the box and Apple devices (HomeKit uses
  mDNS/Bonjour, which does not cross subnets). A Raspberry Pi, NAS or always-on
  Linux box is ideal.

## Install

```bash
git clone https://github.com/alanstrok/liveboxtvuhd.git
cd liveboxtvuhd
python3 -m venv .venv && . .venv/bin/activate
pip install -r homekit/requirements.txt
```

> If the optional `pyqrcode`/`pypng`/`base36` packages fail to build on your
> system, that only disables the terminal QR code — pairing by setup code
> still works.

## Run

Quick start (single channel list, full channel lineup):

```bash
python -m homekit.run --host 192.168.1.20 --country caraibe
```

Or with a config file (recommended, lets you pick channels):

```bash
cp homekit/config.example.yaml homekit/config.yaml
# edit homekit/config.yaml
python -m homekit.run --config homekit/config.yaml
```

On startup it prints a setup code (and a QR code if the optional packages are
installed):

```
====================================================
  Livebox TV UHD HomeKit bridge
  In the Home app: Add Accessory -> More options...
  Setup code: 123-45-678
====================================================
```

In the **Home app**: *Add Accessory → More options…* → pick *Livebox TV* → enter
the setup code. Because it's a set-top box, it shows up with a remote tile and a
channel/input picker.

## Configuration

All options can be set in the YAML file or on the command line (CLI wins). See
[`config.example.yaml`](config.example.yaml).

| Option         | CLI flag           | Default   | Description |
|----------------|--------------------|-----------|-------------|
| `host`         | `--host`           | —         | Box IP/hostname (required) |
| `port`         | `--port`           | `8080`    | Box HTTP port |
| `country`      | `--country`        | `caraibe` | `france` / `caraibe` / `poland` channel list |
| `name`         | `--name`           | `Livebox TV` | Accessory name in Home |
| `poll_interval`| `--poll-interval`  | `10`      | Seconds between state polls |
| `homekit_port` | `--homekit-port`   | `51826`   | Port the HomeKit server listens on |
| `pincode`      | —                  | random    | Fixed `XXX-XX-XXX` setup code |
| `channels`     | —                  | full list | Explicit channel selection (see below) |

The Livebox host can also be supplied via the `LIVEBOX_HOST` environment
variable (handy for Docker).

### Choosing channels (important)

HomeKit allows at most **~96 input sources per accessory**, but a country's
channel list is much longer (Caribbean has 161 tunable channels, France 236,
Poland 209). If you don't pick channels, the bridge exposes the first ~96 and
logs a warning.

For a clean, usable input list, select exactly the channels you watch — by
`index` or by name, in the order you want them shown:

```yaml
channels:
  - 1            # GUADELOUPE 1ERE
  - 11           # TF1
  - FRANCE 2
  - ARTE
  - BEIN SPORTS 1
```

Channels whose `epg_id` is `-1` (apps, the TV guide, regional mosaics) can't be
tuned via the API and are never offered as inputs.

## Run as a service

### systemd

Edit paths/user in [`liveboxtv-homekit.service`](liveboxtv-homekit.service),
then:

```bash
sudo cp homekit/liveboxtv-homekit.service /etc/systemd/system/
sudo systemctl enable --now liveboxtv-homekit
```

### Docker

HomeKit needs the LAN, so use host networking:

```bash
docker build -t liveboxtv-homekit -f homekit/Dockerfile .
docker run -d --name liveboxtv-homekit --network host \
    -e LIVEBOX_HOST=192.168.1.20 -e LIVEBOX_COUNTRY=caraibe \
    -v "$PWD/homekit-data:/data" \
    liveboxtv-homekit
```

## Notes & limitations

- **One accessory per box.** Run multiple instances (different `--persist-file`
  and `--homekit-port`) for several boxes.
- HomeKit volume is **relative** (the box exposes only `VOL+`/`VOL-`), so Home
  shows a stepper, not an absolute slider.
- The box reports power via its `activeStandbyState`; "on" means out of standby.
- This bridge is independent of the Home Assistant integration — you can run
  either or both.

## Troubleshooting

- **Accessory not found in Home app:** the bridge host and your iPhone must be
  on the same subnet; check that mDNS/Bonjour isn't blocked and that
  `homekit_port` (51826) is reachable.
- **"Accessory already added" / re-pairing:** delete the persisted state file
  (e.g. `livebox-homekit.state`) and restart to get a fresh pairing.
- **Channels missing:** you likely hit the ~96-input cap — use the `channels`
  option to choose a subset.
- Run with `-v` for debug logging of every HomeKit call and box request.
