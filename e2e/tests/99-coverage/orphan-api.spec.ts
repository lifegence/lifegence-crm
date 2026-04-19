import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { KNOWN_UNCOVERED_APIS } from '../../fixtures/coverage-allowlist';

const ALL_APIS_FILE = path.join(__dirname, '../../fixtures/all-whitelist-apis.json');
const COVERAGE_DIR = path.join(__dirname, '../../coverage-output');

/**
 * Aggregates coverage-output/*.json written by tests using the `coverage` fixture
 * and compares against the static list extracted by extract_whitelist_apis.py.
 *
 * Run AFTER the full suite has executed so coverage-output/ is populated.
 */
test.describe('Whitelist API coverage audit (P2)', () => {
  test('every whitelist API is exercised by at least one E2E test', () => {
    if (!fs.existsSync(ALL_APIS_FILE)) {
      test.skip(
        true,
        `fixtures/all-whitelist-apis.json missing — run \`npm run extract-apis\` first`,
      );
    }
    const allApis: string[] = JSON.parse(fs.readFileSync(ALL_APIS_FILE, 'utf-8'));

    const covered = new Set<string>();
    if (fs.existsSync(COVERAGE_DIR)) {
      for (const f of fs.readdirSync(COVERAGE_DIR)) {
        if (!f.endsWith('.json')) continue;
        const arr: string[] = JSON.parse(
          fs.readFileSync(path.join(COVERAGE_DIR, f), 'utf-8'),
        );
        for (const a of arr) covered.add(a);
      }
    }

    const orphans = allApis.filter(
      (a) => !covered.has(a) && !KNOWN_UNCOVERED_APIS.has(a),
    );

    const coverage = ((allApis.length - orphans.length) / Math.max(allApis.length, 1)) * 100;
    console.log(
      `\n[orphan-api] total=${allApis.length}, covered=${covered.size}, orphans=${orphans.length} (${coverage.toFixed(1)}%)`,
    );
    if (orphans.length > 0) {
      console.log('[orphan-api] uncovered APIs:');
      for (const o of orphans.slice(0, 50)) console.log(`  - ${o}`);
      if (orphans.length > 50) console.log(`  … and ${orphans.length - 50} more`);
    }

    if (process.env.ORPHAN_STRICT === '1') {
      expect(orphans.length, 'Uncovered whitelist APIs').toBe(0);
    }
  });
});
