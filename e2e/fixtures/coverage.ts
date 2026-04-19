import { test as base } from '@playwright/test';
import { ApiCoverageRecorder } from '../utils/api-coverage-recorder';

/**
 * Extended `test` fixture that auto-records API calls per test.
 * Import this in specs to opt into coverage recording.
 */
export const test = base.extend<{ coverage: ApiCoverageRecorder }>({
  coverage: async ({ page }, use, info) => {
    const rec = new ApiCoverageRecorder();
    rec.attach(page);
    await use(rec);
    rec.saveForTest(info);
  },
});

export { expect } from '@playwright/test';
