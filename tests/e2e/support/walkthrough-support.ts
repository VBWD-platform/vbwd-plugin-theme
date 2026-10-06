/**
 * S152 walkthroughs — what every theme plugin's `walkthrough-<plugin>.spec.ts` shares:
 * the theme-mode gate, the per-step "themed + full-page screenshot" check, and an admin
 * API client that removes everything it created (LIFO) in `afterAll`.
 *
 * Run through vbwd-fe-user `playwright.theme.config.ts` (it maps `@playwright/test` and
 * `@fe-user-e2e/*` into fe-user). The fe-user frontend-mode helpers stay the one home for
 * the theme marker, logins and CMS fixtures; this module only adds the walkthrough layer.
 */
import { expect, request as apiRequest, type APIRequestContext, type Page } from '@playwright/test';
import {
  IS_THEME_MODE,
  THEME_META_SELECTOR,
  loginAdmin,
  uniqueSlug,
} from '@fe-user-e2e/frontend-mode/frontend-mode-support';

export const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8080';
export const WALKTHROUGH_SKIP_REASON =
  'theme walkthroughs need a theme-mode stack: run with E2E_FRONTEND_MODE=theme ' +
  '(see docs/architecture/frontend-modes.md "How to switch locally")';
const SCREENSHOT_DIRECTORY = 'test-results';
const CLEANUP_REASON_LENGTH = 300;

/** Call first inside a walkthrough `describe`: skips every test unless E2E_FRONTEND_MODE=theme. */
export function skipUnlessThemeMode(test: { skip(condition: boolean, description: string): void }): void {
  test.skip(!IS_THEME_MODE, WALKTHROUGH_SKIP_REASON);
}

/** Asserts who rendered the current step and takes `test-results/walkthrough-<plugin>-<step>.png`. */
export class WalkthroughSteps {
  constructor(private readonly pluginName: string) {}

  async themed(page: Page, stepName: string): Promise<void> {
    await expect(page.locator(THEME_META_SELECTOR)).toHaveCount(1);
    await this.screenshot(page, stepName);
  }

  /** A hand-off step the SPA renders on purpose (e.g. `/dashboard`). */
  async spa(page: Page, stepName: string): Promise<void> {
    await expect(page.locator(THEME_META_SELECTOR)).toHaveCount(0);
    await this.screenshot(page, stepName);
  }

  private async screenshot(page: Page, stepName: string): Promise<void> {
    await page.screenshot({
      path: `${SCREENSHOT_DIRECTORY}/walkthrough-${this.pluginName}-${stepName}.png`,
      fullPage: true,
    });
  }
}

type JsonBody = Record<string, any>;

/** Admin-API seeding with LIFO cleanup: every `create` registers the DELETE that undoes it. */
export class AdminSeeder {
  private readonly cleanupSteps: Array<() => Promise<unknown>> = [];

  private constructor(
    readonly request: APIRequestContext,
    readonly adminToken: string,
  ) {}

  static async open(): Promise<AdminSeeder> {
    const request = await apiRequest.newContext({ baseURL: BASE_URL });
    return new AdminSeeder(request, await loginAdmin(request));
  }

  get authHeaders(): Record<string, string> {
    return { Authorization: `Bearer ${this.adminToken}` };
  }

  async send(method: 'GET' | 'POST' | 'PUT' | 'DELETE', path: string, data?: unknown): Promise<JsonBody> {
    const response = await this.request.fetch(path, { method, data, headers: this.authHeaders });
    if (!response.ok()) {
      throw new Error(`${method} ${path} failed: ${response.status()} ${await response.text()}`);
    }
    const text = await response.text();
    return text ? JSON.parse(text) : {};
  }

  /** POSTs `data` to `path`; `afterAll` DELETEs `deletePath(created)`. */
  async create(path: string, data: unknown, deletePath: (created: JsonBody) => string): Promise<JsonBody> {
    const created = await this.send('POST', path, data);
    this.onCleanup(() => this.deleteOrWarn(deletePath(created)));
    return created;
  }

  /** DELETE that never throws (cleanup goes on) but reports what it could not remove. */
  async deleteOrWarn(path: string, data?: unknown): Promise<boolean> {
    const response = await this.request.delete(path, { headers: this.authHeaders, data });
    if (!response.ok()) {
      const reason = (await response.text()).slice(0, CLEANUP_REASON_LENGTH);
      console.warn(`walkthrough cleanup: DELETE ${path} → ${response.status()} ${reason}`);
    }
    return response.ok();
  }

  /** Registers an undo step for something created indirectly (an order, an invoice). */
  onCleanup(step: () => Promise<unknown>): void {
    this.cleanupSteps.push(step);
  }

  async cleanup(): Promise<void> {
    while (this.cleanupSteps.length > 0) {
      const step = this.cleanupSteps.pop() as () => Promise<unknown>;
      await step().catch((error: unknown) => console.warn('walkthrough cleanup step failed:', error));
    }
    await this.request.dispose();
  }

  /** What the merchant does when the bank transfer arrives (activates what the invoice sold). */
  async markInvoicePaid(invoiceId: string): Promise<void> {
    await this.send('POST', `/api/v1/admin/invoices/${invoiceId}/mark-paid`, { payment_reference: 'WALKTHROUGH' });
  }

  /**
   * A buyer of its own, registered through the public API. Its cleanup force-deletes the
   * user with everything the journey bought (invoices, subscriptions, orders), so a
   * purchase never lands on the shared test user. Create it after the things it buys
   * (plans, products): cleanup is LIFO, so the buyer and its purchases go first.
   */
  async freshBuyer(): Promise<WalkthroughBuyer> {
    const buyer = { email: `${uniqueSlug('walkthrough-buyer')}@example.com`, password: WALKTHROUGH_BUYER_PASSWORD };
    const response = await this.request.post('/api/v1/auth/register', { data: buyer });
    if (!response.ok()) {
      throw new Error(`registering ${buyer.email} failed: ${response.status()} ${await response.text()}`);
    }
    const { user_id: userId } = await response.json();
    this.onCleanup(() => this.deleteOrWarn(`/api/v1/admin/users/${userId}`, { force: true }));
    return { ...buyer, userId };
  }
}

const WALKTHROUGH_BUYER_PASSWORD = 'WalkPass123@';

export interface WalkthroughBuyer {
  email: string;
  password: string;
  userId: string;
}

/**
 * For a signed-in viewer the runtime re-renders a CMS page's areas (personalised regions)
 * right after load, replacing their DOM; interact only once that swap has happened.
 */
export async function waitForViewerRegions(page: Page): Promise<void> {
  await expect(page.locator('body')).toHaveAttribute('data-auth', 'user');
}

/** Signs a buyer in through the themed `/login` (it hands off to the SPA `/dashboard`). */
export async function loginInBrowser(page: Page, buyer: { email: string; password: string }): Promise<void> {
  await page.goto('/login');
  await page.fill('[data-testid="email"]', buyer.email);
  await page.fill('[data-testid="password"]', buyer.password);
  await page.click('[data-testid="login-button"]');
  await page.waitForURL('/dashboard');
}

export const CONFIRMATION_URL_PATTERN = /\/checkout\/confirmation\?invoice_id=([0-9a-f-]+)/;

/** The invoice id in `/checkout/confirmation?invoice_id=…` (the page the journey is on). */
export function invoiceIdFromConfirmationUrl(url: string): string {
  const invoiceId = CONFIRMATION_URL_PATTERN.exec(url)?.[1];
  if (!invoiceId) {
    throw new Error(`not a checkout confirmation URL: ${url}`);
  }
  return invoiceId;
}

/** A monthly tariff plan (removed after the buyers that subscribed to it). */
export async function seedTariffPlan(seeder: AdminSeeder, name: string, price: number): Promise<JsonBody> {
  const created = await seeder.create(
    '/api/v1/admin/tarif-plans/',
    { name, slug: uniqueSlug('walkthrough-plan'), description: `${name} — seeded by a walkthrough.`, price, billing_period: 'MONTHLY' },
    (response) => `/api/v1/admin/tarif-plans/${response.plan.id}`,
  );
  return created.plan;
}

/** A percentage coupon on a GLOBAL discount (both removed afterwards). */
export async function seedPercentageCoupon(seeder: AdminSeeder, percent: number): Promise<string> {
  const { discount } = await seeder.create(
    '/api/v1/admin/discounts',
    { name: uniqueSlug('Walkthrough discount'), discount_type: 'PERCENTAGE', value: percent, scope: 'GLOBAL' },
    (response) => `/api/v1/admin/discounts/${response.discount.id}`,
  );
  const code = uniqueSlug('WALK').replace(/-/g, '').toUpperCase();
  await seeder.create('/api/v1/admin/coupons', { code, discount_id: discount.id }, (response) => `/api/v1/admin/coupons/${response.coupon.id}`);
  return code;
}
