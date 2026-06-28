# homebridge-liveboxtvuhd

A [Homebridge](https://homebridge.io) plugin that exposes the **Orange Livebox
TV UHD** set-top box (Orange **France**, **Caribbean** and **Poland**) to Apple
HomeKit as a native **TV Set-Top Box** accessory — power, channel inputs, volume
and the Control-Center remote, all from the Home app and Siri.

It controls the box over its local HTTP remote-control API
(`http://<box>:8080/remoteControl/cmd`), the same protocol as the
[Home Assistant integration](../README.md), and shares the exact same channel
lists (generated from the integration's data).

> Each box is published as an **external accessory** (HomeKit only allows one
> Television per bridge). After installing and restarting, you add it in the
> Home app as a separate tile using your **Homebridge PIN** — it's still managed
> from the Homebridge UI.

---

## Install on Unraid (Homebridge Docker)

These steps assume the **Homebridge** container from Unraid *Community
Applications* (the official `homebridge/homebridge` image with the Config UI).

The plugin lives in a subfolder of this repo and isn't on the npm registry yet,
so install it from source. npm can't install a subfolder straight from a git
URL, so use one of these:

### Option 1 — Build a tarball, then install it (most reliable)

On any machine with Node 18+ and Python 3:

```sh
git clone https://github.com/alanstrok/liveboxtvuhd.git
cd liveboxtvuhd/homebridge
npm install        # builds dist/ via the prepare script
npm pack           # produces homebridge-liveboxtvuhd-1.0.0.tgz
```

Copy the `.tgz` into your Homebridge appdata (e.g.
`/mnt/user/appdata/homebridge/`). Then open the **Homebridge UI**
(`http://<unraid-ip>:8581`) → top-right **⋮ → Terminal** and run:

```sh
npm install -g /homebridge/homebridge-liveboxtvuhd-1.0.0.tgz
```

Restart Homebridge (UI: power icon → *Restart*).

> `/homebridge` is the persisted config volume inside the official image; adjust
> if your Unraid template maps it elsewhere (e.g. `/var/lib/homebridge`).

### Option 2 — Clone and install locally (if the container has git)

In the Homebridge **Terminal**:

```sh
cd /homebridge
git clone https://github.com/alanstrok/liveboxtvuhd.git
npm install -g ./liveboxtvuhd/homebridge   # the prepare script builds it
```

Restart Homebridge. (This pulls TypeScript to compile on install, so the
container needs internet access — it normally has it.)

### Option 3 — Publish to npm (one-click updates later)

If you want it searchable/updatable in the Homebridge UI like other plugins,
`npm publish` it to your own npm account (rename the package if you wish). Then
install it normally from **Plugins → search**.

---

## Configure

After install, the **Plugins** tab shows *Orange Livebox TV UHD* with a
**Settings** (gear) button — the form is provided by the plugin. Fill in:

- **Name** — what shows in the Home app (e.g. `Livebox Salon`).
- **Host / IP** — the box's address (give it a DHCP reservation so it's stable).
- **Country** — `Caribbean`, `France` or `Poland` (channel list).
- **Channels** *(recommended)* — the channels to expose, by number or name.

Or edit `config.json` directly:

```json
{
  "platforms": [
    {
      "platform": "LiveboxTvUhd",
      "devices": [
        {
          "name": "Livebox Salon",
          "host": "192.168.1.20",
          "country": "caraibe",
          "pollInterval": 10,
          "channels": ["1", "11", "FRANCE 2", "ARTE", "BEIN SPORTS 1"]
        }
      ]
    }
  ]
}
```

Restart Homebridge after changing the config.

### Choosing channels (important)

HomeKit allows at most **~96 input sources per accessory**, but a country's
channel list is much longer (Caribbean 161 tunable channels, France 236, Poland
209). If you leave **Channels** empty, the plugin exposes the first ~96 and logs
a warning. For a clean input list, list just the channels you watch, in the
order you want them — by number (`index`) or name. Channels that can't be tuned
via the API (apps, the TV guide, regional mosaics) are never offered.

---

## Pair in the Home app

1. After the restart, open the **Home** app → **Add Accessory**.
2. Choose **More options…** — *Livebox Salon* appears as an uncertified
   accessory.
3. Enter your **Homebridge PIN** (the one on the Homebridge UI status page /
   the bridge QR code). External accessories share the bridge's PIN.
4. It's added as a **set-top box**, with a power tile and the Apple TV Remote in
   Control Center.

| HomeKit control | Box action |
|---|---|
| Power on / off | `POWER` (standby toggle) |
| Input picker | Tune to the selected channel |
| Remote D-pad / OK / Back / Menu | Cursor keys / OK / Back / Menu |
| Play-Pause, Rewind, Fast-forward | Media keys |
| Info button | TV guide |
| Volume +/- (in the remote) | `VOL+` / `VOL-` |
| ⏭ / ⏮ on the remote | Channel up / down |

The plugin polls the box (every 10 s by default) so the power state and current
channel stay in sync in Home.

---

## Multiple boxes

Add more entries to **devices** — each becomes its own set-top box accessory,
with its own channel selection.

## Troubleshooting

- **Accessory doesn't appear in Home:** it's an *external* accessory — use
  *Add Accessory → More options…*, not the QR scanner alone. Your iPhone and the
  Homebridge host must be on the same subnet (HomeKit uses mDNS/Bonjour).
- **"Already added" / want to re-pair:** remove the accessory in Home, then in
  the Homebridge UI go to the box's settings and it will re-publish on restart.
- **Box shows as off when it isn't / commands time out:** confirm the IP and
  that `http://<box>:8080/remoteControl/cmd?operation=10` returns JSON from the
  Homebridge host. Increase **timeout** if the box is slow.
- **Channels missing:** you hit the ~96-input cap — set the **Channels** option.
- Enable Homebridge **debug** logging to see every HomeKit call and box request.

## Development

```sh
cd homebridge
npm install
npm run build           # compile TypeScript -> dist/
npm run gen-channels    # regenerate src/channels.ts from the integration
```

The channel lists are generated from
`custom_components/liveboxtvuhd/const_<country>.py` via
[`tools/gen-channels.py`](../tools/gen-channels.py) so the plugin never drifts
from the Home Assistant integration.
