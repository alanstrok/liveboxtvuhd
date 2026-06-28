import type { API } from 'homebridge';

import { PLATFORM_NAME } from './settings';
import { LiveboxPlatform } from './platform';

/** Homebridge entry point: register the platform. */
export = (api: API): void => {
  api.registerPlatform(PLATFORM_NAME, LiveboxPlatform);
};
