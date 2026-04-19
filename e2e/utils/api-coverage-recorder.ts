import { Page, TestInfo } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Records which Frappe whitelist API endpoints are called during a test.
 * Combined with static extraction, this lets us find APIs that no test exercises.
 */
export class ApiCoverageRecorder {
  private calls = new Set<string>();

  attach(page: Page): void {
    page.on('request', (req) => {
      const m = req.url().match(/\/api\/method\/([\w.]+)/);
      if (m) this.calls.add(m[1]);
    });
  }

  saveForTest(info: TestInfo, outDir = 'coverage-output'): void {
    fs.mkdirSync(outDir, { recursive: true });
    const safeId = info.titlePath.join('__').replace(/[^\w.-]/g, '_').slice(0, 200);
    const file = path.join(outDir, `${safeId}.json`);
    fs.writeFileSync(file, JSON.stringify([...this.calls].sort(), null, 2));
  }
}
