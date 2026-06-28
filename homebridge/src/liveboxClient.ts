import type { Logger } from 'homebridge';

import { Channel, Country, CHANNELS } from './channels';

// Livebox remote-control operations.
const OPERATION_INFORMATION = '10';
const OPERATION_CHANNEL_CHANGE = '09';
const OPERATION_KEYPRESS = '01';

// Remote-control key codes (subset used by the plugin).
export const KEYS: Record<string, number> = {
  POWER: 116,
  'CH+': 402,
  'CH-': 403,
  'VOL+': 115,
  'VOL-': 114,
  MUTE: 113,
  UP: 103,
  DOWN: 108,
  LEFT: 105,
  RIGHT: 106,
  OK: 352,
  BACK: 158,
  MENU: 139,
  'PLAY/PAUSE': 164,
  FBWD: 168,
  FFWD: 159,
  GUIDE: 365,
};

export interface LiveboxState {
  reachable: boolean;
  on: boolean;
  epgId: string | null;
  mediaState: string | null;
  macAddress: string | null;
}

/**
 * Dependency-free client for the Orange Livebox TV UHD set-top box.
 *
 * Talks to the box's local HTTP remote-control endpoint:
 *   http://<host>:<port>/remoteControl/cmd?operation=...
 * This is a TypeScript port of the control parts of the Home Assistant
 * integration's client.py (EPG/now-playing enrichment is intentionally
 * omitted - HomeKit TV accessories don't use it).
 */
export class LiveboxClient {
  public readonly channels: Channel[];
  private standby = '1'; // '0' == on, '1' == standby
  private epgId: string | null = null;
  private mediaState: string | null = null;
  private macAddress: string | null = null;
  private reachable = false;

  constructor(
    private readonly host: string,
    private readonly port: number,
    country: Country,
    private readonly timeoutMs: number,
    private readonly log: Logger,
  ) {
    this.channels = CHANNELS[country];
  }

  get isOn(): boolean {
    return this.standby === '0';
  }

  get currentEpgId(): string | null {
    return this.epgId;
  }

  get mac(): string | null {
    return this.macAddress;
  }

  channelByEpgId(epgId: string): Channel | undefined {
    return this.channels.find((c) => c.epg_id === epgId);
  }

  channelByIndex(index: string): Channel | undefined {
    return this.channels.find((c) => c.index === index);
  }

  /** Poll the box for its current state. */
  async update(): Promise<LiveboxState> {
    const data = await this.request(OPERATION_INFORMATION);
    if (!data) {
      this.reachable = false;
      this.standby = '1';
      return this.snapshot();
    }
    const result = data?.result?.data ?? {};
    this.reachable = true;
    this.standby = result.activeStandbyState ?? '1';
    this.epgId = result.playedMediaId ?? null;
    this.mediaState = result.playedMediaState ?? null;
    if (result.macAddress) {
      this.macAddress = result.macAddress;
    }
    return this.snapshot();
  }

  async turnOn(): Promise<void> {
    if (!this.isOn) {
      await this.pressKey('POWER');
    }
  }

  async turnOff(): Promise<void> {
    if (this.isOn) {
      await this.pressKey('POWER');
    }
  }

  async setChannelByEpgId(epgId: string): Promise<boolean> {
    if (epgId === '-1' || epgId === '') {
      return false;
    }
    const padded = epgId.padStart(10, '*');
    const res = await this.request(OPERATION_CHANNEL_CHANGE, {
      epg_id: padded,
      uui: '1',
    });
    return res !== null;
  }

  async pressKey(key: string, mode = 0): Promise<void> {
    const code = KEYS[key];
    if (code === undefined) {
      this.log.debug(`Unknown key ${key}`);
      return;
    }
    await this.request(OPERATION_KEYPRESS, { key: String(code), mode: String(mode) });
  }

  async volumeUp(): Promise<void> {
    await this.pressKey('VOL+');
  }

  async volumeDown(): Promise<void> {
    await this.pressKey('VOL-');
  }

  async mute(): Promise<void> {
    await this.pressKey('MUTE');
  }

  private snapshot(): LiveboxState {
    return {
      reachable: this.reachable,
      on: this.isOn,
      epgId: this.epgId,
      mediaState: this.mediaState,
      macAddress: this.macAddress,
    };
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private async request(operation: string, params?: Record<string, string>): Promise<any> {
    const url = new URL(`http://${this.host}:${this.port}/remoteControl/cmd`);
    url.searchParams.set('operation', operation);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        url.searchParams.set(k, v);
      }
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const resp = await fetch(url, { signal: controller.signal });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      return await resp.json();
    } catch (err) {
      this.standby = '1';
      this.reachable = false;
      this.log.debug(`Livebox request failed (op=${operation}): ${(err as Error).message}`);
      return null;
    } finally {
      clearTimeout(timer);
    }
  }
}
