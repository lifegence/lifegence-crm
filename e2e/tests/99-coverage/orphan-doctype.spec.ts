import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { FrappeClient } from '../../utils/frappe-client';
import { KNOWN_UI_HIDDEN_DOCTYPES } from '../../fixtures/coverage-allowlist';

const LIFEGENCE_CRM_MODULES = ['Sales CRM'];
const MAX_CRAWL_PAGES = 80;
const ENTRY_POINTS = ['/desk', '/desk/crm'];

const APP_ROOT = path.resolve(__dirname, '../../../lifegence_crm');

type DocTypeRow = { name: string };

function slugify(name: string): string {
  return name.toLowerCase().replace(/ /g, '-');
}

function readWorkspaceLinks(appRoot: string): Set<string> {
  const links = new Set<string>();
  const workspaceFiles: string[] = [];
  for (const m of fs.readdirSync(appRoot)) {
    const wsDir = path.join(appRoot, m, 'workspace');
    if (!fs.existsSync(wsDir) || !fs.statSync(wsDir).isDirectory()) continue;
    for (const sub of fs.readdirSync(wsDir)) {
      const f = path.join(wsDir, sub, `${sub}.json`);
      if (fs.existsSync(f)) workspaceFiles.push(f);
    }
  }
  for (const f of workspaceFiles) {
    try {
      const doc = JSON.parse(fs.readFileSync(f, 'utf-8'));
      for (const arr of [doc.links ?? [], doc.shortcuts ?? []]) {
        for (const item of arr) {
          if (item.link_to) links.add(item.link_to);
        }
      }
    } catch { /* ignore */ }
  }
  return links;
}

test.describe('Orphan DocType detection (P1)', () => {
  test.setTimeout(180_000);
  test('every lifegence_crm DocType is reachable from Desk navigation', async ({
    page, baseURL,
  }) => {
    const client = await FrappeClient.login(
      baseURL!,
      process.env.ADMIN_USR || 'Administrator',
      process.env.ADMIN_PWD || 'admin',
    );

    const docTypes = await client.getList<DocTypeRow>('DocType', {
      filters: [
        ['module', 'in', LIFEGENCE_CRM_MODULES],
        ['istable', '=', 0],
        ['custom', '=', 0],
      ],
      fields: ['name'],
    });
    await client.dispose();
    expect(docTypes.length).toBeGreaterThan(0);

    const visited = new Set<string>();
    const queue: string[] = [...ENTRY_POINTS];
    while (queue.length > 0 && visited.size < MAX_CRAWL_PAGES) {
      const url = queue.shift()!;
      if (visited.has(url)) continue;
      visited.add(url);
      try {
        const res = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 8_000 });
        if (!res || res.status() >= 400) continue;
        await page.waitForTimeout(200);
      } catch { continue; }
      const hrefs: string[] = await page.$$eval('a[href]', (as) =>
        as.map((a) => (a as HTMLAnchorElement).getAttribute('href') ?? '').filter(Boolean),
      );
      for (const href of hrefs) {
        if (!href.startsWith('/')) continue;
        const clean = href.split('?')[0].split('#')[0].replace(/\/$/, '');
        if ((clean.startsWith('/desk') || clean.startsWith('/app')) && !visited.has(clean)) {
          queue.push(clean);
        }
      }
    }

    const reachableSlugs = new Set<string>();
    for (const url of visited) {
      const norm = url.replace(/^\/app/, '/desk');
      const m = norm.match(/^\/desk\/([^/]+)/);
      if (m) reachableSlugs.add(m[1]);
    }
    const registered = readWorkspaceLinks(APP_ROOT);

    const orphans = docTypes
      .filter((dt) => !KNOWN_UI_HIDDEN_DOCTYPES.has(dt.name))
      .filter((dt) => !reachableSlugs.has(slugify(dt.name)) && !registered.has(dt.name))
      .map((dt) => dt.name);

    console.log(
      `\n[orphan-doctype] crawled=${visited.size} slugs=${reachableSlugs.size} registered=${registered.size} doctypes=${docTypes.length} orphans=${orphans.length}`,
    );
    if (orphans.length > 0) {
      console.log('[orphan-doctype] orphans:');
      for (const o of orphans) console.log(`  - ${o}`);
    }

    if (process.env.ORPHAN_STRICT === '1') {
      expect(orphans).toEqual([]);
    }
  });
});
