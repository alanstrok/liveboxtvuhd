"""Standalone client for the Orange Livebox TV UHD set-top box.

This is a dependency-free (no Home Assistant) re-implementation of the control
parts of ``custom_components/liveboxtvuhd/client.py``. It talks to the box's
local HTTP remote-control endpoint:

    http://<host>:<port>/remoteControl/cmd?operation=...

EPG / "now playing" enrichment is intentionally omitted: HomeKit TV
accessories only expose power, input (channel) selection, volume and remote
keys, none of which need the EPG.
"""
from __future__ import annotations

import logging
from collections import OrderedDict

import requests

from .channels import get_channels

_LOGGER = logging.getLogger(__name__)

# Livebox operations
OPERATION_INFORMATION = "10"
OPERATION_CHANNEL_CHANGE = "09"
OPERATION_KEYPRESS = "01"

# Remote-control key codes
KEYS = {
    "POWER": 116,
    "0": 512, "1": 513, "2": 514, "3": 515, "4": 516,
    "5": 517, "6": 518, "7": 519, "8": 520, "9": 521,
    "CH+": 402,
    "CH-": 403,
    "VOL+": 115,
    "VOL-": 114,
    "MUTE": 113,
    "UP": 103,
    "DOWN": 108,
    "LEFT": 105,
    "RIGHT": 106,
    "OK": 352,
    "BACK": 158,
    "MENU": 139,
    "PLAY/PAUSE": 164,
    "FBWD": 168,
    "FFWD": 159,
    "REC": 167,
    "VOD": 393,
    "GUIDE": 365,
}


class LiveboxClient:
    """Minimal HTTP control client for the Livebox TV UHD."""

    def __init__(self, host: str, port: int = 8080, country: str = "caraibe", timeout: int = 3):
        self.host = host
        self.port = port
        self.country = country
        self.timeout = timeout
        self.channels = get_channels(country)

        self._standby_state = "1"   # "0" == on, "1" == standby
        self._channel_id = None     # current epg_id, or "-1" for apps/home
        self._media_state = None    # "PLAY" / "PAUSE" / None
        self._mac_address = None
        self._reachable = False

    # ------------------------------------------------------------------ state

    @property
    def is_on(self) -> bool:
        return self._standby_state == "0"

    @property
    def reachable(self) -> bool:
        return self._reachable

    @property
    def channel_id(self):
        return self._channel_id

    @property
    def media_state(self):
        return self._media_state

    @property
    def mac_address(self):
        return self._mac_address

    def update(self) -> bool:
        """Poll the box for its current state. Returns True if reachable."""
        data = self._request(OPERATION_INFORMATION)
        if not data:
            self._reachable = False
            self._standby_state = "1"
            return False

        result = data.get("result", {}).get("data", {})
        self._reachable = True
        self._standby_state = result.get("activeStandbyState", "1")
        self._channel_id = result.get("playedMediaId")
        self._media_state = result.get("playedMediaState")
        if "macAddress" in result:
            self._mac_address = result["macAddress"]
        return True

    # ---------------------------------------------------------------- channels

    def get_channel_by_epg_id(self, epg_id):
        for chan in self.channels:
            if chan["epg_id"] == str(epg_id):
                return chan
        return None

    def get_channel_by_index(self, index):
        for chan in self.channels:
            if chan["index"] == str(index):
                return chan
        return None

    def set_channel_by_epg_id(self, epg_id) -> bool:
        """Tune to a channel. The epg_id is padded to 10 chars with '*'."""
        if str(epg_id) == "-1":
            _LOGGER.debug("Channel epg_id=-1 is not tunable, ignoring")
            return False
        epg_id_str = str(epg_id).rjust(10, "*")
        return bool(
            self._request(
                OPERATION_CHANNEL_CHANGE,
                OrderedDict([("epg_id", epg_id_str), ("uui", "1")]),
            )
        )

    # -------------------------------------------------------------------- keys

    def press_key(self, key, mode: int = 0):
        if isinstance(key, str):
            assert key in KEYS, f"No such key: {key}"
            key = KEYS[key]
        return self._request(
            OPERATION_KEYPRESS, OrderedDict([("key", key), ("mode", mode)])
        )

    def turn_on(self):
        if not self.is_on:
            self.press_key("POWER")

    def turn_off(self):
        if self.is_on:
            self.press_key("POWER")

    def volume_up(self):
        self.press_key("VOL+")

    def volume_down(self):
        self.press_key("VOL-")

    def mute(self):
        self.press_key("MUTE")

    def channel_up(self):
        self.press_key("CH+")

    def channel_down(self):
        self.press_key("CH-")

    def play_pause(self):
        self.press_key("PLAY/PAUSE")

    # ----------------------------------------------------------------- private

    def _request(self, operation: str, params=None):
        url = f"http://{self.host}:{self.port}/remoteControl/cmd"
        get_params = OrderedDict({"operation": operation})
        if params:
            get_params.update(params)
        try:
            resp = requests.get(url, params=get_params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            self._standby_state = "1"
            self._reachable = False
            _LOGGER.debug("Livebox request failed (%s): %s", operation, err)
            return None
