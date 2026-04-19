import { test as setup, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const ENV = process.env.TEST_ENV || 'local';
const AUTH_DIR = '.auth';
fs.mkdirSync(AUTH_DIR, { recursive: true });

type UserCreds = { key: string; usr: string; pwd: string };

const users: UserCreds[] = [
  {
    key: 'admin',
    usr: process.env.ADMIN_USR || 'Administrator',
    pwd: process.env.ADMIN_PWD || 'admin',
  },
  {
    key: 'user1',
    usr: process.env.USER1_USR || 'e2e-user1@lifegence.test',
    pwd: process.env.USER1_PWD || 'e2etest123',
  },
  {
    key: 'user2',
    usr: process.env.USER2_USR || 'e2e-user2@lifegence.test',
    pwd: process.env.USER2_PWD || 'e2etest123',
  },
];

for (const u of users) {
  setup(`authenticate ${u.key}`, async ({ page, context }) => {
    await page.goto('/login');

    const emailInput = page.locator('input[type="email"], input#login_email, input[name="usr"]').first();
    const pwdInput = page.locator('input[type="password"]').first();
    await emailInput.waitFor({ state: 'visible', timeout: 15_000 });
    await emailInput.fill(u.usr);
    await pwdInput.fill(u.pwd);

    const submit = page.locator('button[type="submit"], .btn-login').first();
    await submit.click();

    // Post-login lands on the Desk UI. In Frappe 16.12+ the canonical
    // path is /desk/* and /app/* is a 301 redirect to /desk/*.
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30_000 });

    await page.goto('/desk');
    await expect(page).toHaveURL(/\/desk/, { timeout: 15_000 });

    const statePath = path.join(AUTH_DIR, `${u.key}.${ENV}.json`);
    await context.storageState({ path: statePath });
    console.log(`✓ saved session for ${u.key} → ${statePath}`);
  });
}
