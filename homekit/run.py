#!/usr/bin/env python3
"""Run the Orange Livebox TV UHD HomeKit bridge.

Starts a standalone HomeKit accessory (HAP-python) that presents the Livebox
TV UHD set-top box to Apple Home. Pair it from the Home app like any other
HomeKit accessory using the setup code printed at startup.

Examples
--------
    python -m homekit.run --host 192.168.1.20
    python -m homekit.run --config homekit/config.yaml
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys

try:
    from .accessory import LiveboxSetTopBox
    from .client import LiveboxClient
    from .config import (
        DEFAULT_HOMEKIT_PORT,
        load_config,
    )
except ImportError:
    # Allow running as a plain script: `python homekit/run.py`
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from homekit.accessory import LiveboxSetTopBox
    from homekit.client import LiveboxClient
    from homekit.config import (
        DEFAULT_HOMEKIT_PORT,
        load_config,
    )

_LOGGER = logging.getLogger("livebox_homekit")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="HomeKit bridge for the Orange Livebox TV UHD set-top box."
    )
    parser.add_argument("--config", help="Path to a YAML config file")
    parser.add_argument("--host", help="Livebox IP address or hostname")
    parser.add_argument("--port", type=int, help="Livebox HTTP port (default 8080)")
    parser.add_argument(
        "--country",
        choices=["france", "caraibe", "poland"],
        help="Channel list to use (default caraibe)",
    )
    parser.add_argument("--name", help="Accessory name shown in Apple Home")
    parser.add_argument(
        "--homekit-port", type=int,
        help=f"Port for the HomeKit server (default {DEFAULT_HOMEKIT_PORT})",
    )
    parser.add_argument(
        "--persist-file", default="livebox-homekit.state",
        help="File used to store HomeKit pairing state",
    )
    parser.add_argument(
        "--poll-interval", type=int,
        help="Seconds between state polls of the box (default 10)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(
            path=args.config,
            host=args.host,
            port=args.port,
            country=args.country,
            name=args.name,
            homekit_port=args.homekit_port,
            poll_interval=args.poll_interval,
        )
    except (ValueError, FileNotFoundError) as err:
        _LOGGER.error("Configuration error: %s", err)
        _LOGGER.error(
            "Provide --host (and optionally --country) or a --config file. "
            "See homekit/config.example.yaml."
        )
        return 2

    try:
        from pyhap.accessory_driver import AccessoryDriver
    except ImportError:
        _LOGGER.error(
            "HAP-python is not installed. Install dependencies with "
            "'pip install -r homekit/requirements.txt'"
        )
        return 1

    client = LiveboxClient(config.host, config.port, config.country)
    # Best-effort initial poll so the accessory can use the box's MAC as a
    # stable serial number; failure here is fine (the box may be in standby).
    try:
        client.update()
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Initial Livebox poll failed; continuing")

    channels = config.resolve_channels()
    _LOGGER.info(
        "Starting Livebox HomeKit bridge for %s:%s (country=%s, %d channels)",
        config.host, config.port, config.country, len(channels),
    )

    driver = AccessoryDriver(
        port=config.homekit_port,
        persist_file=args.persist_file,
        pincode=config.pincode.encode() if config.pincode else None,
    )
    accessory = LiveboxSetTopBox(
        driver,
        client=client,
        display_name=config.name,
        channels=channels,
        poll_interval=config.poll_interval,
    )
    driver.add_accessory(accessory=accessory)

    _print_pairing_info(driver, accessory)

    signal.signal(signal.SIGTERM, driver.signal_handler)
    signal.signal(signal.SIGINT, driver.signal_handler)
    driver.start()
    return 0


def _print_pairing_info(driver, accessory) -> None:
    try:
        pincode = driver.state.pincode.decode()
    except Exception:  # noqa: BLE001
        pincode = "(see logs)"
    print("\n" + "=" * 52)
    print("  Livebox TV UHD HomeKit bridge")
    print("  In the Home app: Add Accessory -> More options...")
    print(f"  Setup code: {pincode}")
    try:
        import pyqrcode  # type: ignore

        uri = accessory.xhm_uri()
        print("\n  Or scan this QR code:\n")
        print(pyqrcode.create(uri).terminal(quiet_zone=2))
    except Exception:  # noqa: BLE001 - QR is optional
        print("  (install 'pyqrcode pypng base36' to show a scannable QR code)")
    print("=" * 52 + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
