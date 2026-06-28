import type { CharacteristicValue, PlatformAccessory, Service } from 'homebridge';

import type { LiveboxPlatform } from './platform';
import { Channel, Country, tunableChannels } from './channels';
import { LiveboxClient } from './liveboxClient';

/**
 * A HomeKit accessory may expose at most 100 services (Television,
 * TelevisionSpeaker, AccessoryInformation and the HAP protocol service take a
 * few, and iOS gets unreliable near the ceiling), so cap channel inputs with
 * comfortable headroom. Curate the list via the "channels" option for a usable
 * input picker.
 */
const MAX_INPUT_SOURCES = 90;

/**
 * Make a channel name acceptable as a HomeKit name characteristic. HAP v2
 * rejects names that don't start/end with a letter or number, or that contain
 * symbols like '+', '/' or ':' - which would otherwise prevent the whole
 * accessory from being added to the Home app. e.g. "LIGUE 1+" -> "LIGUE 1 Plus",
 * "PUBLIC SENAT 24/24" -> "PUBLIC SENAT 24 24".
 */
export function sanitizeName(raw: string): string {
  const cleaned = raw
    .replace(/\+/g, ' Plus ')
    .replace(/&/g, ' and ')
    .replace(/[^A-Za-z0-9 '.,-]/g, ' ') // drop '/', ':', and other symbols
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[^A-Za-z0-9]+/, '') // must start with a letter/number
    .replace(/[^A-Za-z0-9]+$/, ''); // must end with a letter/number
  return cleaned.length > 0 ? cleaned : 'Channel';
}

export interface DeviceConfig {
  name: string;
  host: string;
  port?: number;
  country?: Country;
  channels?: (string | number)[];
  pollInterval?: number;
  timeout?: number;
}

export class LiveboxSetTopBox {
  private readonly client: LiveboxClient;
  private readonly tvService: Service;
  private readonly idToChannel = new Map<number, Channel>();
  private readonly epgToId = new Map<string, number>();
  private readonly pollIntervalMs: number;
  private pollTimer?: NodeJS.Timeout;

  constructor(
    private readonly platform: LiveboxPlatform,
    private readonly accessory: PlatformAccessory,
    device: DeviceConfig,
  ) {
    const { Service, Characteristic } = this.platform;
    const country: Country = device.country ?? 'caraibe';
    const port = device.port ?? 8080;
    const timeout = (device.timeout ?? 3) * 1000;
    this.pollIntervalMs = (device.pollInterval ?? 10) * 1000;

    this.client = new LiveboxClient(device.host, port, country, timeout, this.platform.log);

    // --- Accessory information ---------------------------------------------
    this.accessory
      .getService(Service.AccessoryInformation)!
      .setCharacteristic(Characteristic.Manufacturer, 'Orange')
      .setCharacteristic(Characteristic.Model, 'Livebox TV UHD')
      .setCharacteristic(
        Characteristic.SerialNumber,
        this.client.mac ?? `livebox-${device.host}`,
      );

    // --- Television service -------------------------------------------------
    this.tvService =
      this.accessory.getService(Service.Television) ||
      this.accessory.addService(Service.Television, device.name);

    this.tvService
      .setCharacteristic(Characteristic.ConfiguredName, device.name)
      .setCharacteristic(
        Characteristic.SleepDiscoveryMode,
        Characteristic.SleepDiscoveryMode.ALWAYS_DISCOVERABLE,
      );

    this.tvService
      .getCharacteristic(Characteristic.Active)
      .onSet(this.setActive.bind(this));

    this.tvService
      .getCharacteristic(Characteristic.ActiveIdentifier)
      .onSet(this.setActiveIdentifier.bind(this));

    this.tvService
      .getCharacteristic(Characteristic.RemoteKey)
      .onSet(this.setRemoteKey.bind(this));

    // --- Channel inputs -----------------------------------------------------
    this.addChannelInputs(device, country);

    // --- Speaker (volume +/- and mute) -------------------------------------
    const speaker =
      this.accessory.getService(Service.TelevisionSpeaker) ||
      this.accessory.addService(Service.TelevisionSpeaker, `${device.name} Speaker`);
    speaker
      .setCharacteristic(Characteristic.Active, Characteristic.Active.ACTIVE)
      .setCharacteristic(
        Characteristic.VolumeControlType,
        Characteristic.VolumeControlType.RELATIVE,
      );
    speaker
      .getCharacteristic(Characteristic.VolumeSelector)
      .onSet(this.setVolume.bind(this));
    speaker
      .getCharacteristic(Characteristic.Mute)
      .onSet(this.setMute.bind(this));
    this.tvService.addLinkedService(speaker);

    this.startPolling();
  }

  private addChannelInputs(device: DeviceConfig, country: Country): void {
    const { Service, Characteristic } = this.platform;
    let channels = this.resolveChannels(device, country);

    if (channels.length > MAX_INPUT_SOURCES) {
      this.platform.log.warn(
        `${device.name}: ${channels.length} channels requested but HomeKit ` +
          `allows at most ${MAX_INPUT_SOURCES} inputs per accessory; exposing ` +
          `the first ${MAX_INPUT_SOURCES}. Use the "channels" option to choose ` +
          'exactly which channels to expose.',
      );
      channels = channels.slice(0, MAX_INPUT_SOURCES);
    }

    channels.forEach((chan, i) => {
      const identifier = i + 1;
      const subtype = `input-${identifier}`;
      const displayName = sanitizeName(chan.name);
      const input =
        this.accessory.getServiceById(Service.InputSource, subtype) ||
        this.accessory.addService(Service.InputSource, displayName, subtype);
      input
        .setCharacteristic(Characteristic.Identifier, identifier)
        .setCharacteristic(Characteristic.ConfiguredName, displayName)
        .setCharacteristic(
          Characteristic.IsConfigured,
          Characteristic.IsConfigured.CONFIGURED,
        )
        .setCharacteristic(
          Characteristic.InputSourceType,
          Characteristic.InputSourceType.TUNER,
        )
        .setCharacteristic(
          Characteristic.CurrentVisibilityState,
          Characteristic.CurrentVisibilityState.SHOWN,
        );
      this.tvService.addLinkedService(input);
      this.idToChannel.set(identifier, chan);
      this.epgToId.set(chan.epg_id, identifier);
    });

    this.platform.log.info(
      `${device.name}: exposed ${channels.length} channels as HomeKit inputs`,
    );
  }

  /** Build the ordered channel list, honouring an explicit selection. */
  private resolveChannels(device: DeviceConfig, country: Country): Channel[] {
    const tunable = tunableChannels(country);
    if (!device.channels || device.channels.length === 0) {
      return tunable;
    }
    const byIndex = new Map(tunable.map((c) => [c.index, c]));
    const byName = new Map(tunable.map((c) => [c.name.toLowerCase(), c]));
    const selected: Channel[] = [];
    for (const ref of device.channels) {
      const key = String(ref).trim();
      const chan = byIndex.get(key) || byName.get(key.toLowerCase());
      if (chan) {
        selected.push(chan);
      } else {
        this.platform.log.warn(`${device.name}: channel "${ref}" not found, skipping`);
      }
    }
    if (selected.length === 0) {
      this.platform.log.warn(
        `${device.name}: no configured channels matched; using full list`,
      );
      return tunable;
    }
    return selected;
  }

  // --- HomeKit setters ------------------------------------------------------

  private async setActive(value: CharacteristicValue): Promise<void> {
    this.platform.log.debug(`Set Active=${value}`);
    if (value === this.platform.Characteristic.Active.ACTIVE) {
      await this.client.turnOn();
    } else {
      await this.client.turnOff();
    }
  }

  private async setActiveIdentifier(value: CharacteristicValue): Promise<void> {
    const chan = this.idToChannel.get(Number(value));
    if (!chan) {
      this.platform.log.warn(`Unknown input identifier ${value}`);
      return;
    }
    this.platform.log.debug(`Select input ${value} (${chan.name})`);
    await this.client.setChannelByEpgId(chan.epg_id);
  }

  private async setRemoteKey(value: CharacteristicValue): Promise<void> {
    const { Characteristic } = this.platform;
    const map: Record<number, string> = {
      [Characteristic.RemoteKey.REWIND]: 'FBWD',
      [Characteristic.RemoteKey.FAST_FORWARD]: 'FFWD',
      [Characteristic.RemoteKey.NEXT_TRACK]: 'CH+',
      [Characteristic.RemoteKey.PREVIOUS_TRACK]: 'CH-',
      [Characteristic.RemoteKey.ARROW_UP]: 'UP',
      [Characteristic.RemoteKey.ARROW_DOWN]: 'DOWN',
      [Characteristic.RemoteKey.ARROW_LEFT]: 'LEFT',
      [Characteristic.RemoteKey.ARROW_RIGHT]: 'RIGHT',
      [Characteristic.RemoteKey.SELECT]: 'OK',
      [Characteristic.RemoteKey.BACK]: 'BACK',
      [Characteristic.RemoteKey.EXIT]: 'MENU',
      [Characteristic.RemoteKey.PLAY_PAUSE]: 'PLAY/PAUSE',
      [Characteristic.RemoteKey.INFORMATION]: 'GUIDE',
    };
    const key = map[Number(value)];
    if (!key) {
      this.platform.log.debug(`Unmapped RemoteKey ${value}`);
      return;
    }
    await this.client.pressKey(key);
  }

  private async setVolume(value: CharacteristicValue): Promise<void> {
    if (value === this.platform.Characteristic.VolumeSelector.INCREMENT) {
      await this.client.volumeUp();
    } else {
      await this.client.volumeDown();
    }
  }

  private async setMute(): Promise<void> {
    await this.client.mute();
  }

  // --- Polling --------------------------------------------------------------

  private startPolling(): void {
    const poll = async () => {
      try {
        await this.poll();
      } catch (err) {
        this.platform.log.debug(`Poll error: ${(err as Error).message}`);
      }
    };
    void poll();
    this.pollTimer = setInterval(poll, this.pollIntervalMs);
    // Don't keep the Homebridge process alive solely for this timer.
    this.pollTimer.unref?.();
  }

  private async poll(): Promise<void> {
    const { Characteristic } = this.platform;
    const state = await this.client.update();

    const active = state.reachable && state.on
      ? Characteristic.Active.ACTIVE
      : Characteristic.Active.INACTIVE;
    this.tvService.updateCharacteristic(Characteristic.Active, active);

    if (state.epgId && this.epgToId.has(state.epgId)) {
      this.tvService.updateCharacteristic(
        Characteristic.ActiveIdentifier,
        this.epgToId.get(state.epgId)!,
      );
    }
  }
}
