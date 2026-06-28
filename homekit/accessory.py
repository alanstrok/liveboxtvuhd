"""HomeKit accessory exposing the Orange Livebox TV UHD as a Set-Top Box."""
from __future__ import annotations

import logging

from pyhap.accessory import Accessory
from pyhap.util import event_wait

from .client import LiveboxClient

_LOGGER = logging.getLogger(__name__)

# HAP accessory category for a TV set-top box (HomeKit shows the set-top-box
# tile/icon and groups it under the TV section). pyhap doesn't ship a named
# constant for it, so we use the raw HAP category id.
CATEGORY_TV_SET_TOP_BOX = 35

# InputSourceType.TUNER — these inputs are broadcast TV channels.
INPUT_SOURCE_TUNER = 2

# VolumeControlType.RELATIVE — the box only supports volume +/- (no absolute).
VOLUME_CONTROL_RELATIVE = 1

# A HomeKit accessory may expose at most 100 services. We reserve a handful for
# the Television, TelevisionSpeaker, AccessoryInformation and HAP protocol
# services, leaving this many for channel inputs.
MAX_INPUT_SOURCES = 96

# HomeKit RemoteKey codes -> Livebox key names (Control Center remote).
REMOTE_KEY_MAP = {
    0: "FBWD",        # Rewind
    1: "FFWD",        # Fast forward
    2: "CH+",         # Next track  -> channel up
    3: "CH-",         # Previous track -> channel down
    4: "UP",          # Arrow up
    5: "DOWN",        # Arrow down
    6: "LEFT",        # Arrow left
    7: "RIGHT",       # Arrow right
    8: "OK",          # Select
    9: "BACK",        # Back
    10: "MENU",       # Exit -> menu
    11: "PLAY/PAUSE",  # Play/Pause
    15: "GUIDE",      # Information -> TV guide
}

# VolumeSelector codes: 0 == increment, 1 == decrement.
VOLUME_INCREMENT = 0


class LiveboxSetTopBox(Accessory):
    """A HomeKit Television accessory presented as a set-top box."""

    category = CATEGORY_TV_SET_TOP_BOX

    def __init__(self, driver, client: LiveboxClient, display_name: str,
                 channels: list[dict], poll_interval: int = 10, **kwargs):
        super().__init__(driver, display_name, **kwargs)

        self.client = client
        self._poll_interval = poll_interval
        self._display_name = display_name

        # Map of HomeKit input identifier -> channel dict, and the reverse
        # (epg_id -> identifier) used to reflect the box's current channel.
        self._id_to_channel: dict[int, dict] = {}
        self._epg_to_id: dict[str, int] = {}

        self.set_info_service(
            manufacturer="Orange",
            model="Livebox TV UHD",
            serial_number=client.mac_address or f"livebox-{client.host}",
            firmware_revision="1.0",
        )

        # --- Television service -------------------------------------------
        tv = self.add_preload_service(
            "Television",
            ["Name", "ConfiguredName", "Active", "ActiveIdentifier",
             "RemoteKey", "SleepDiscoveryMode"],
        )
        self._char_active = tv.configure_char(
            "Active", value=0, setter_callback=self._set_active
        )
        self._char_active_id = tv.configure_char(
            "ActiveIdentifier", value=0,
            setter_callback=self._set_active_identifier,
        )
        tv.configure_char("Name", value=display_name)
        tv.configure_char("ConfiguredName", value=display_name)
        # SleepDiscoveryMode.ALWAYS_DISCOVERABLE
        tv.configure_char("SleepDiscoveryMode", value=1)
        tv.configure_char("RemoteKey", setter_callback=self._set_remote_key)
        self._tv_service = tv

        # --- Input sources (channels) -------------------------------------
        self._add_channel_inputs(tv, channels)

        # --- Speaker service (volume +/- and mute) ------------------------
        speaker = self.add_preload_service(
            "TelevisionSpeaker",
            ["Active", "VolumeControlType", "VolumeSelector", "Mute"],
        )
        speaker.configure_char("Active", value=1)
        speaker.configure_char("VolumeControlType", value=VOLUME_CONTROL_RELATIVE)
        speaker.configure_char(
            "VolumeSelector", setter_callback=self._set_volume_selector
        )
        speaker.configure_char("Mute", setter_callback=self._set_mute)
        tv.add_linked_service(speaker)

    # ------------------------------------------------------------------ setup

    def _add_channel_inputs(self, tv_service, channels: list[dict]) -> None:
        """Create one InputSource service per channel."""
        if len(channels) > MAX_INPUT_SOURCES:
            _LOGGER.warning(
                "%d channels requested but HomeKit allows at most %d input "
                "sources per accessory; exposing the first %d. Use the "
                "'channels' config option to choose exactly which channels to "
                "expose.",
                len(channels), MAX_INPUT_SOURCES, MAX_INPUT_SOURCES,
            )
            channels = channels[:MAX_INPUT_SOURCES]

        for identifier, chan in enumerate(channels, start=1):
            name = chan["name"]
            source = self.add_preload_service(
                "InputSource", ["Name", "Identifier", "ConfiguredName",
                                "InputSourceType", "IsConfigured",
                                "CurrentVisibilityState"],
            )
            source.configure_char("Name", value=name)
            source.configure_char("Identifier", value=identifier)
            source.configure_char("ConfiguredName", value=name)
            source.configure_char("InputSourceType", value=INPUT_SOURCE_TUNER)
            source.configure_char("IsConfigured", value=1)
            source.configure_char("CurrentVisibilityState", value=0)
            tv_service.add_linked_service(source)

            self._id_to_channel[identifier] = chan
            self._epg_to_id[str(chan["epg_id"])] = identifier

        _LOGGER.info("Exposed %d channels as HomeKit inputs", len(channels))

    # --------------------------------------------------------------- setters
    # These are called from HomeKit (the Home app / Siri / Control Center).

    def _set_active(self, value):
        _LOGGER.debug("HomeKit set Active=%s", value)
        if value:
            self.client.turn_on()
        else:
            self.client.turn_off()

    def _set_active_identifier(self, value):
        chan = self._id_to_channel.get(value)
        if not chan:
            _LOGGER.warning("Unknown input identifier %s", value)
            return
        _LOGGER.debug("HomeKit select input %s (%s)", value, chan["name"])
        self.client.set_channel_by_epg_id(chan["epg_id"])

    def _set_remote_key(self, value):
        key = REMOTE_KEY_MAP.get(value)
        if key is None:
            _LOGGER.debug("Unmapped RemoteKey %s", value)
            return
        _LOGGER.debug("HomeKit RemoteKey %s -> %s", value, key)
        self.client.press_key(key)

    def _set_volume_selector(self, value):
        if value == VOLUME_INCREMENT:
            self.client.volume_up()
        else:
            self.client.volume_down()

    def _set_mute(self, value):
        # The box only has a mute toggle; honour any mute/unmute press.
        self.client.mute()

    # ----------------------------------------------------------------- update

    async def run(self):
        """Poll the box and reflect its state back into HomeKit.

        Invoked once by the driver at startup; loops until the driver's stop
        event is set, sleeping ``poll_interval`` seconds between polls but
        waking immediately on shutdown.
        """
        while not self.driver.aio_stop_event.is_set():
            try:
                await self._poll_once()
            except Exception:  # noqa: BLE001 - never let polling kill the loop
                _LOGGER.exception("Error while polling the Livebox")
            if await event_wait(self.driver.aio_stop_event, self._poll_interval):
                break

    async def _poll_once(self):
        """Poll the box and reflect its state back into HomeKit."""
        loop = self.driver.loop
        reachable = await loop.run_in_executor(None, self.client.update)
        if not reachable:
            # Box unreachable -> report as off so HomeKit stays in sync.
            if self._char_active.get_value() != 0:
                self._char_active.set_value(0)
            return

        active = 1 if self.client.is_on else 0
        if self._char_active.get_value() != active:
            self._char_active.set_value(active)

        epg_id = str(self.client.channel_id) if self.client.channel_id else None
        if epg_id and epg_id in self._epg_to_id:
            identifier = self._epg_to_id[epg_id]
            if self._char_active_id.get_value() != identifier:
                self._char_active_id.set_value(identifier)
