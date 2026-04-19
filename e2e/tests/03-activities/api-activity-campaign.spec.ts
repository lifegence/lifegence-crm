import { test, expect } from '../../fixtures/coverage';
import { FrappeClient } from '../../utils/frappe-client';

test.describe('Activity + Campaign — list smoke (P1)', () => {
  let client: FrappeClient;

  test.beforeAll(async ({ baseURL }) => {
    client = await FrappeClient.login(
      baseURL!,
      process.env.ADMIN_USR || 'Administrator',
      process.env.ADMIN_PWD || 'admin',
    );
  });

  test.afterAll(async () => await client.dispose());

  test('Activity list is accessible', async () => {
    const list = await client.getList<{ name: string }>('Activity', {
      fields: ['name'],
      limit_page_length: 5,
    });
    expect(Array.isArray(list)).toBe(true);
  });

  test('Campaign list is accessible', async () => {
    const list = await client.getList<{ name: string }>('Campaign', {
      fields: ['name'],
      limit_page_length: 5,
    });
    expect(Array.isArray(list)).toBe(true);
  });

  test('Pipeline Board list is accessible', async () => {
    const list = await client.getList<{ name: string }>('Pipeline Board', {
      fields: ['name'],
      limit_page_length: 5,
    });
    expect(Array.isArray(list)).toBe(true);
  });

  test('Lead Scoring Rule list is accessible', async () => {
    const list = await client.getList<{ name: string }>('Lead Scoring Rule', {
      fields: ['name'],
      limit_page_length: 5,
    });
    expect(Array.isArray(list)).toBe(true);
  });
});
