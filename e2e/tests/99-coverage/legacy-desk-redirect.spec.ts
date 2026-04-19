import { test, expect } from '@playwright/test';

/**
 * Frappe 16.12+ routing: /desk/* is canonical; /app/* 301 redirects to /desk/*.
 * Defined in `frappe/hooks.py` → `website_redirects`.
 * This test guards against regressions in either direction.
 */
const LEGACY_PATHS = [
  { legacy: '/app', canonical: '/desk' },
  { legacy: '/apps', canonical: '/desk' },
  { legacy: '/app/chat', canonical: '/desk/chat' },
  { legacy: '/app/mind-analyzer', canonical: '/desk/mind-analyzer' },
  { legacy: '/app/ai-agent', canonical: '/desk/ai-agent' },
];

test.describe('Legacy /app/* → /desk/* redirect (P2)', () => {
  for (const { legacy, canonical } of LEGACY_PATHS) {
    test(`${legacy} redirects to ${canonical}`, async ({ page }) => {
      const res = await page.goto(legacy, { waitUntil: 'domcontentloaded' });
      expect(res, `no response for ${legacy}`).not.toBeNull();
      await expect(page).toHaveURL(new RegExp(canonical.replace(/\//g, '\\/')), {
        timeout: 15_000,
      });
    });
  }
});
