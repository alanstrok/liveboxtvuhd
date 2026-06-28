#!/usr/bin/env python3
"""Generate the Homebridge plugin's channel data from the integration.

Reads custom_components/liveboxtvuhd/const_<country>.py (the single source of
truth for channel lists) and emits homebridge/src/channels.ts so the Homebridge
plugin and the Home Assistant integration never drift apart.

Usage (from the repo root):
    python3 tools/gen-channels.py > homebridge/src/channels.ts
"""
import importlib.util
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(REPO, "custom_components", "liveboxtvuhd")


def load(country):
    path = os.path.join(BASE, f"const_{country}.py")
    spec = importlib.util.spec_from_file_location(f"const_{country}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CHANNELS


def main():
    out = [
        "// AUTO-GENERATED from custom_components/liveboxtvuhd/const_<country>.py",
        "// Do not edit by hand. Regenerate with tools/gen-channels.py",
        "export interface Channel { index: string; epg_id: string; name: string; }",
        "export type Country = 'france' | 'caraibe' | 'poland';",
        "",
    ]
    for country in ("france", "caraibe", "poland"):
        out.append(f"export const {country.upper()}: Channel[] = [")
        for c in load(country):
            name = c["name"].replace("\\", "\\\\").replace("'", "\\'")
            out.append(
                f"  {{ index: '{c['index']}', epg_id: '{c['epg_id']}', "
                f"name: '{name}' }},"
            )
        out.append("];")
        out.append("")
    out.append(
        "export const CHANNELS: Record<Country, Channel[]> = "
        "{ france: FRANCE, caraibe: CARAIBE, poland: POLAND };"
    )
    out.append("")
    out.append("export function tunableChannels(country: Country): Channel[] {")
    out.append(
        "  return CHANNELS[country].filter((c) => c.epg_id !== '-1' && c.epg_id !== '');"
    )
    out.append("}")
    out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main()
