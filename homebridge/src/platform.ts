import type {
  API,
  Characteristic,
  DynamicPlatformPlugin,
  Logger,
  PlatformAccessory,
  PlatformConfig,
  Service,
} from 'homebridge';

import { PLATFORM_NAME, PLUGIN_NAME } from './settings';
import { DeviceConfig, LiveboxSetTopBox } from './platformAccessory';

/**
 * Homebridge dynamic platform for Orange Livebox TV UHD set-top boxes.
 *
 * Each configured box is published as an *external* accessory (HomeKit only
 * allows one Television per bridge), so it appears as its own set-top box tile
 * in the Home app while still being managed by Homebridge.
 */
export class LiveboxPlatform implements DynamicPlatformPlugin {
  public readonly Service: typeof Service;
  public readonly Characteristic: typeof Characteristic;

  constructor(
    public readonly log: Logger,
    public readonly config: PlatformConfig,
    public readonly api: API,
  ) {
    this.Service = api.hap.Service;
    this.Characteristic = api.hap.Characteristic;

    this.api.on('didFinishLaunching', () => {
      this.publishDevices();
    });
  }

  /**
   * Required by DynamicPlatformPlugin. External (TV) accessories are not
   * restored from cache, so there is nothing to do here.
   */
  configureAccessory(_accessory: PlatformAccessory): void {
    // no-op
  }

  private publishDevices(): void {
    const devices: DeviceConfig[] = Array.isArray(this.config.devices)
      ? this.config.devices
      : [];

    if (devices.length === 0) {
      this.log.warn(
        'No devices configured. Add at least one box under "devices" ' +
          '(name + host) in the plugin settings.',
      );
      return;
    }

    const externalAccessories: PlatformAccessory[] = [];
    for (const device of devices) {
      if (!device.host || !device.name) {
        this.log.error(`Skipping a device entry missing "name" or "host": ${JSON.stringify(device)}`);
        continue;
      }
      const uuid = this.api.hap.uuid.generate(`${PLUGIN_NAME}:${device.name}:${device.host}`);
      const accessory = new this.api.platformAccessory(
        device.name,
        uuid,
        this.api.hap.Categories.TV_SET_TOP_BOX,
      );
      new LiveboxSetTopBox(this, accessory, device);
      externalAccessories.push(accessory);
      this.log.info(`Publishing Livebox set-top box "${device.name}" (${device.host})`);
    }

    if (externalAccessories.length > 0) {
      this.api.publishExternalAccessories(PLUGIN_NAME, externalAccessories);
    }
  }
}
