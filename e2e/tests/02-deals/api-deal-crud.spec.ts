import { test, expect } from '../../fixtures/coverage';
import { FrappeClient } from '../../utils/frappe-client';

test.describe('Deal — DocType CRUD (P0)', () => {
  let client: FrappeClient;
  const created: string[] = [];

  test.beforeAll(async ({ baseURL }) => {
    client = await FrappeClient.login(
      baseURL!,
      process.env.ADMIN_USR || 'Administrator',
      process.env.ADMIN_PWD || 'admin',
    );
  });

  test.afterAll(async () => {
    for (const name of created) {
      try {
        await client.call('frappe.client.delete', { doctype: 'Deal', name });
      } catch { /* ignore */ }
    }
    await client.dispose();
  });

  test('create + get + delete a Deal', async () => {
    // Deal requires a Deal Stage; pick the first one seeded during install.
    const stages = await client.getList<{ name: string }>('Deal Stage', {
      fields: ['name'],
      limit_page_length: 1,
    });
    test.skip(stages.length === 0, 'no Deal Stage seeded');
    const stage = stages[0].name;

    const doc = await client.call<{ name: string }>('frappe.client.insert', {
      doc: {
        doctype: 'Deal',
        deal_name: `e2e-deal-${Date.now()}`,
        stage,
        expected_value: 100000,
      },
    });
    expect(doc.name).toBeTruthy();
    created.push(doc.name);

    const fetched = await client.call<{ name: string; deal_name?: string }>(
      'frappe.client.get',
      { doctype: 'Deal', name: doc.name },
    );
    expect(fetched.name).toBe(doc.name);
  });

  test('list Deals', async () => {
    const list = await client.getList<{ name: string }>('Deal', {
      fields: ['name', 'deal_name'],
      limit_page_length: 10,
      order_by: 'creation desc',
    });
    expect(Array.isArray(list)).toBe(true);
  });

  test('list Deal Stages (seed data)', async () => {
    const stages = await client.getList<{ name: string }>('Deal Stage', {
      fields: ['name'],
      limit_page_length: 20,
    });
    expect(Array.isArray(stages)).toBe(true);
  });
});
