"""Channel lists for the HomeKit bridge.

To keep a single source of truth, the channel definitions are loaded directly
from the Home Assistant integration's ``const_<country>.py`` files (which are
plain data modules with no Home Assistant dependency). This way the HomeKit
bridge always stays in sync with the integration's channel lists.
"""
from __future__ import annotations

import importlib.util
import os

# Repo layout:  <repo>/homekit/channels.py
#               <repo>/custom_components/liveboxtvuhd/const_<country>.py
_HERE = os.path.dirname(os.path.abspath(__file__))
_CONST_DIR = os.path.join(
    _HERE, os.pardir, "custom_components", "liveboxtvuhd"
)

SUPPORTED_COUNTRIES = ("france", "caraibe", "poland")


def _load_const(country: str):
    """Load the ``const_<country>`` data module by file path."""
    if country not in SUPPORTED_COUNTRIES:
        raise ValueError(
            f"Unsupported country '{country}'. "
            f"Choose one of: {', '.join(SUPPORTED_COUNTRIES)}"
        )
    path = os.path.normpath(os.path.join(_CONST_DIR, f"const_{country}.py"))
    spec = importlib.util.spec_from_file_location(f"const_{country}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_channels(country: str) -> list[dict]:
    """Return the raw channel list (list of dicts) for a country."""
    return _load_const(country).CHANNELS


def get_tunable_channels(country: str) -> list[dict]:
    """Return only the channels that can actually be tuned to.

    Channels with ``epg_id == "-1"`` are placeholders / apps (e.g. Netflix,
    the TV guide, regional mosaics) that the box cannot zap to via the
    channel-change API, so they make poor HomeKit inputs and are skipped.
    """
    return [c for c in get_channels(country) if c.get("epg_id") not in (None, "-1")]
