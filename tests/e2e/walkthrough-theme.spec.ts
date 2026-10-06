/**
 * S152 walkthrough @theme — the theme platform itself: the mode probe, the themed `/login`
 * (error, then success), the language switcher + `vbwd_lang` cookie, a personalised
 * region re-rendered for the signed-in viewer, and logout back to the anonymous region.
 *
 * Seeds (admin API, removed afterwards): an English + German page in one translation
 * group whose layout holds an upsell for the anonymous `new` level and a member note for
 * the `logged-in` level.
 */
import { randomUUID } from 'node:crypto';
import { test, expect } from '@playwright/test';
import {
  CmsAdminFixtures,
  MODE_PROBE_PATH,
  TEST_USER,
  accessLevelIdsBySlug,
  uniqueSlug,
} from '@fe-user-e2e/frontend-mode/frontend-mode-support';
import { AdminSeeder, BASE_URL, WalkthroughSteps, skipUnlessThemeMode } from './support/walkthrough-support';

const ANONYMOUS_LEVEL_SLUG = 'new';
const DEFAULT_USER_LEVEL_SLUG = 'logged-in';
const GERMAN_LOGIN_BUTTON = 'Anmelden';
const WRONG_PASSWORD = 'definitely-not-the-password';

test.describe('Walkthrough @theme — login, language, personalised region, logout', () => {
  skipUnlessThemeMode(test);

  const steps = new WalkthroughSteps('theme');
  const upsellText = uniqueSlug('Walkthrough upsell');
  const memberText = uniqueSlug('Walkthrough member note');
  let seeder: AdminSeeder;
  let cms: CmsAdminFixtures;
  let englishSlug: string;
  let germanSlug: string;

  test.beforeAll(async () => {
    seeder = await AdminSeeder.open();
    cms = new CmsAdminFixtures(seeder.request, seeder.adminToken);
    seeder.onCleanup(() => cms.cleanup());
    const levelIds = await accessLevelIdsBySlug(seeder.request, seeder.adminToken);
    const upsell = await cms.htmlWidget(`<p data-testid="walkthrough-upsell">${upsellText}</p>`);
    const memberNote = await cms.htmlWidget(`<p data-testid="walkthrough-member-note">${memberText}</p>`);
    const layout = await cms.layout(
      [
        { name: 'main', type: 'content' },
        { name: 'upsell', type: 'header' },
        { name: 'members', type: 'header' },
      ],
      [
        { widget_id: upsell.id, area_name: 'upsell', sort_order: 0, required_access_level_ids: [levelIds[ANONYMOUS_LEVEL_SLUG]] },
        { widget_id: memberNote.id, area_name: 'members', sort_order: 0, required_access_level_ids: [levelIds[DEFAULT_USER_LEVEL_SLUG]] },
      ],
    );
    const translationGroupId = randomUUID();
    englishSlug = (await cms.post({
      title: uniqueSlug('Walkthrough welcome'),
      language: 'en',
      translation_group_id: translationGroupId,
      layout_id: layout.id,
      content_html: '<p>Welcome to the themed walkthrough.</p>',
    })).slug;
    germanSlug = (await cms.post({
      title: uniqueSlug('Walkthrough Willkommen'),
      language: 'de',
      translation_group_id: translationGroupId,
      layout_id: layout.id,
      content_html: '<p>Willkommen zum Rundgang.</p>',
    })).slug;
  });

  test.afterAll(async () => {
    await seeder?.cleanup();
  });

  test('a visitor signs in on the themed pages, switches language and signs out @theme', async ({ page, context }) => {
    const probe = await page.request.get(MODE_PROBE_PATH);
    expect(probe.status()).toBe(200);
    expect(await probe.json()).toEqual({ mode: 'theme' });

    await page.goto(`/${englishSlug}`);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.locator('[data-testid="walkthrough-upsell"]')).toHaveText(upsellText);
    await expect(page.locator('[data-testid="walkthrough-member-note"]')).toHaveCount(0);
    await steps.themed(page, '01-anonymous-page');

    await page.locator('[data-testid="language-switch-de"]').click();
    await page.waitForURL(new RegExp(`/${germanSlug}$`));
    await expect(page.locator('html')).toHaveAttribute('lang', 'de');
    const languageCookie = (await context.cookies()).find((cookie) => cookie.name === 'vbwd_lang');
    expect(languageCookie?.value).toBe('de');
    await steps.themed(page, '02-german-translation');

    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'de');
    await expect(page.locator('[data-testid="login-button"]')).toHaveText(GERMAN_LOGIN_BUTTON);
    await page.fill('[data-testid="email"]', TEST_USER.email);
    await page.fill('[data-testid="password"]', WRONG_PASSWORD);
    await page.click('[data-testid="login-button"]');
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
    await steps.themed(page, '03-login-error-german');

    await context.addCookies([{ name: 'vbwd_lang', value: 'en', url: BASE_URL }]);
    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await page.fill('[data-testid="email"]', TEST_USER.email);
    await page.fill('[data-testid="password"]', TEST_USER.password);
    await steps.themed(page, '04-login-filled');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL('/dashboard');
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
    await steps.spa(page, '05-dashboard-handoff');

    await page.goto(`/${englishSlug}`);
    await expect(page.locator('[data-testid="walkthrough-member-note"]')).toHaveText(memberText);
    await expect(page.locator('[data-testid="walkthrough-upsell"]')).toHaveCount(0);
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'user');
    await steps.themed(page, '06-personalised-region');

    await page.goto('/dashboard');
    await page.click('[data-testid="user-menu"]');
    await page.click('[data-testid="logout-button"]');
    await expect(page).toHaveURL(/\/login/);
    await page.goto(`/${englishSlug}`);
    await expect(page.locator('[data-testid="walkthrough-upsell"]')).toHaveText(upsellText);
    await expect(page.locator('[data-testid="walkthrough-member-note"]')).toHaveCount(0);
    await steps.themed(page, '07-signed-out');
  });
});
