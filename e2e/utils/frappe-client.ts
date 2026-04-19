import { APIRequestContext, request } from '@playwright/test';

/**
 * Lightweight wrapper around Frappe's REST API.
 * Uses the session cookie (sid) after login.
 */
export class FrappeClient {
  private constructor(
    private ctx: APIRequestContext,
    public baseUrl: string,
  ) {}

  static async login(baseUrl: string, usr: string, pwd: string): Promise<FrappeClient> {
    const ctx = await request.newContext({
      baseURL: baseUrl,
      ignoreHTTPSErrors: true,
    });
    const res = await ctx.post('/api/method/login', {
      form: { usr, pwd },
    });
    if (!res.ok()) {
      throw new Error(`Login failed for ${usr}: ${res.status()} ${await res.text()}`);
    }
    return new FrappeClient(ctx, baseUrl);
  }

  /** Call a whitelisted method via /api/method/<dotted>. Returns `message` field. */
  async call<T = unknown>(method: string, args: Record<string, unknown> = {}): Promise<T> {
    const data: Record<string, string> = {};
    for (const [k, v] of Object.entries(args)) {
      data[k] = typeof v === 'string' ? v : JSON.stringify(v);
    }
    const res = await this.ctx.post(`/api/method/${method}`, { form: data });
    if (!res.ok()) {
      throw new Error(
        `${method} failed: ${res.status()}\n${await res.text().catch(() => '')}`,
      );
    }
    const body = (await res.json()) as { message?: T };
    return body.message as T;
  }

  /** Generic Frappe list helper. */
  async getList<T = Record<string, unknown>>(
    doctype: string,
    opts: {
      filters?: unknown;
      fields?: string[];
      limit_page_length?: number;
      order_by?: string;
    } = {},
  ): Promise<T[]> {
    return this.call<T[]>('frappe.client.get_list', {
      doctype,
      filters: opts.filters ?? [],
      fields: opts.fields ?? ['name'],
      limit_page_length: opts.limit_page_length ?? 0,
      order_by: opts.order_by ?? 'modified desc',
    });
  }

  async dispose(): Promise<void> {
    await this.ctx.dispose();
  }
}
