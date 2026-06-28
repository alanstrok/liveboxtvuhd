"""Configuration loading for the Livebox HomeKit bridge."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from .channels import SUPPORTED_COUNTRIES, get_tunable_channels

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8080
DEFAULT_COUNTRY = "caraibe"
DEFAULT_NAME = "Livebox TV"
DEFAULT_HOMEKIT_PORT = 51826
DEFAULT_POLL_INTERVAL = 10


@dataclass
class Config:
    host: str
    port: int = DEFAULT_PORT
    country: str = DEFAULT_COUNTRY
    name: str = DEFAULT_NAME
    # Optional explicit channel selection (list of channel "index" values or
    # names). When empty, the country's full tunable channel list is used
    # (truncated to HomeKit's input-source limit).
    channels: list = field(default_factory=list)
    homekit_port: int = DEFAULT_HOMEKIT_PORT
    poll_interval: int = DEFAULT_POLL_INTERVAL
    pincode: str | None = None

    def __post_init__(self):
        if not self.host:
            raise ValueError("'host' is required")
        if self.country not in SUPPORTED_COUNTRIES:
            raise ValueError(
                f"'country' must be one of {SUPPORTED_COUNTRIES}, "
                f"got '{self.country}'"
            )

    def resolve_channels(self) -> list[dict]:
        """Return the ordered list of channel dicts to expose as inputs."""
        tunable = get_tunable_channels(self.country)
        if not self.channels:
            return tunable

        by_index = {c["index"]: c for c in tunable}
        by_name = {c["name"].lower(): c for c in tunable}
        selected: list[dict] = []
        for ref in self.channels:
            ref_str = str(ref).strip()
            chan = by_index.get(ref_str) or by_name.get(ref_str.lower())
            if chan is None:
                _LOGGER.warning("Configured channel '%s' not found, skipping", ref)
                continue
            selected.append(chan)
        if not selected:
            _LOGGER.warning(
                "None of the configured channels matched; falling back to the "
                "full channel list"
            )
            return tunable
        return selected


def load_config(path: str | None = None, **overrides) -> Config:
    """Load configuration from an optional YAML file plus keyword overrides.

    Keyword overrides (e.g. from the command line) take precedence over the
    file. ``None`` overrides are ignored.
    """
    data: dict = {}
    if path:
        data = _load_yaml(path)

    for key, value in overrides.items():
        if value is not None:
            data[key] = value

    # Allow a Livebox host to be supplied via the environment for container use.
    data.setdefault("host", os.environ.get("LIVEBOX_HOST"))

    known = {f for f in Config.__dataclass_fields__}  # noqa: C416
    unknown = set(data) - known
    if unknown:
        _LOGGER.warning("Ignoring unknown config keys: %s", ", ".join(sorted(unknown)))
    data = {k: v for k, v in data.items() if k in known}

    return Config(**data)


def _load_yaml(path: str) -> dict:
    try:
        import yaml
    except ImportError as err:  # pragma: no cover
        raise SystemExit(
            "PyYAML is required to read a config file. Install it with "
            "'pip install pyyaml', or pass options on the command line."
        ) from err
    with open(path, "r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    if not isinstance(loaded, dict):
        raise SystemExit(f"Config file {path} must contain a YAML mapping")
    return loaded
