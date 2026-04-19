import { test, expect } from '@playwright/test';

test.describe('CRM — Auth + Desk landing (P0) @smoke', () => {
  test('authenticated session reaches /desk', async ({ page }) => {
    await page.goto('/desk');
    await expect(page).toHaveURL(/\/desk/);
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('CRM workspace page loads', async ({ page }) => {
    await page.goto('/desk/crm');
    await expect(page).toHaveURL(/\/desk\/crm/);
  });

  test('Deal list page loads', async ({ page }) => {
    await page.goto('/desk/deal');
    await expect(page).toHaveURL(/\/desk\/deal/);
  });
});
