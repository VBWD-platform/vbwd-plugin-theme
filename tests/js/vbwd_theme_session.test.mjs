// S152-07 — vbwd-theme.js session + cart directives, run with
// `node --test 'plugins/theme/tests/js/*.test.mjs'`.
//
// Mirrors of the SPA sources (DRIFT NOTE: keep in step with them):
//   isTokenExpired / purge          — vue/src/api/token.ts + api/index.ts isAuthenticated()
//   guest-only /login               — vue/src/router/index.ts authNavigationGuard (login && authenticated)
//   auth-required pages (/pay/*)    — the same guard (requiresAuth && !authenticated)
//   session keys + redirect         — vue/src/views/Login.vue handleLogin, components/checkout/EmailBlock.vue
//   cart hydrate / clear            — plugins/checkout/draftCheckout.ts, CheckoutConfirmationView.vue
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const RUNTIME_SCRIPT_PATH = fileURLToPath(
  new URL('../../theme/themes/basic/static/_shared/js/vbwd-theme.js', import.meta.url),
);
const SITE_ORIGIN = 'https://shop.example';
const NOW_SECONDS = Math.floor(Date.now() / 1000);

function jwt(payload) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.sig`;
}
const LIVE_TOKEN = jwt({ exp: NOW_SECONDS + 3600, sub: 'u-1' });
const EXPIRED_TOKEN = jwt({ exp: NOW_SECONDS - 3600, sub: 'u-1' });

function createStorage(initialEntries = {}) {
  const entries = new Map(Object.entries(initialEntries));
  return {
    getItem: (key) => (entries.has(key) ? entries.get(key) : null),
    setItem: (key, value) => entries.set(key, String(value)),
    removeItem: (key) => entries.delete(key),
    keys: () => [...entries.keys()].sort(),
  };
}

// A tiny DOM: elements with attributes, a parent chain, and `[attr]` / `[attr="v"]` selectors.
function matches(element, selector) {
  const parsed = /^\[([a-z-]+)(?:="([^"]*)")?\]$/.exec(selector);
  if (!parsed) return false;
  const [, name, value] = parsed;
  return element.attributes.has(name) && (value === undefined || element.attributes.get(name) === value);
}

function createElement(attributes = {}, { textContent = '', parent = null } = {}) {
  const element = {
    attributes: new Map(Object.entries(attributes)),
    textContent,
    parent,
    removed: false,
    getAttribute(name) {
      return this.attributes.has(name) ? this.attributes.get(name) : null;
    },
    hasAttribute(name) {
      return this.attributes.has(name);
    },
    setAttribute(name, value) {
      this.attributes.set(name, String(value));
    },
    closest(selector) {
      for (let current = this; current; current = current.parent) {
        if (matches(current, selector)) return current;
      }
      return null;
    },
    remove() {
      this.removed = true;
    },
  };
  return element;
}

function createDocument({ bodyAttributes = {}, elements = [] } = {}) {
  const listenersByType = {};
  const dispatched = [];
  const body = createElement(bodyAttributes);
  body.dispatchEvent = (event) => {
    dispatched.push({ target: 'body', type: event.type, detail: event.detail });
    return true;
  };
  const document = {
    readyState: 'complete',
    body,
    elements,
    dispatched,
    querySelectorAll: (selector) =>
      elements.filter((element) => !element.removed && matches(element, selector)),
    addEventListener(type, listener) {
      (listenersByType[type] = listenersByType[type] || []).push(listener);
    },
    dispatchEvent(event) {
      dispatched.push({ target: 'document', type: event.type, detail: event.detail });
      (listenersByType[event.type] || []).forEach((listener) => listener(event));
      return true;
    },
  };
  return document;
}

function createLocation(pathAndQuery = '/') {
  const url = new URL(pathAndQuery, SITE_ORIGIN);
  return {
    origin: url.origin,
    href: url.href,
    pathname: url.pathname,
    search: url.search,
    assignedUrls: [],
    replacedUrls: [],
    assign(target) {
      this.assignedUrls.push(target);
    },
    replace(target) {
      this.replacedUrls.push(target);
    },
  };
}

function createFetchStub() {
  const calls = [];
  const fetchStub = (url, options) => {
    calls.push({ url, options });
    return Promise.resolve({ status: 200, ok: true, json: () => Promise.resolve({ regions: {} }) });
  };
  fetchStub.calls = calls;
  return fetchStub;
}

function loadRuntime({
  storageEntries = {},
  sessionEntries = {},
  pathAndQuery = '/',
  bodyAttributes = {},
  elements = [],
  fetchStub,
} = {}) {
  const storage = createStorage(storageEntries);
  const sessionStorage = createStorage(sessionEntries);
  const document = createDocument({ bodyAttributes, elements });
  const location = createLocation(pathAndQuery);
  const context = {
    document,
    localStorage: storage,
    sessionStorage,
    location,
    URL,
    CustomEvent,
    Promise,
    atob,
    JSON,
    Date,
  };
  if (fetchStub) context.fetch = fetchStub;
  context.window = context;
  vm.createContext(context);
  vm.runInContext(readFileSync(RUNTIME_SCRIPT_PATH, 'utf8'), context, { filename: 'vbwd-theme.js' });
  return { VbwdTheme: context.VbwdTheme, storage, sessionStorage, document, location };
}

const plain = (value) => JSON.parse(JSON.stringify(value));
const SESSION_ENTRIES = (token) => ({
  auth_token: token,
  user: '{"id":"u-1"}',
  user_id: 'u-1',
  user_permissions: '["*"]',
  vbwd_cart: '[{"type":"PLAN","id":"p","name":"Pro","price":9,"quantity":1}]',
});

// ── token expiry (token.ts) ──────────────────────────────────────────────────

test('isTokenExpired mirrors token.ts: only a decodable past exp is expired', () => {
  const { VbwdTheme } = loadRuntime();

  assert.equal(VbwdTheme.isTokenExpired(EXPIRED_TOKEN), true);
  assert.equal(VbwdTheme.isTokenExpired(LIVE_TOKEN), false);
  assert.equal(VbwdTheme.isTokenExpired('header.payload.signature'), false);
  assert.equal(VbwdTheme.isTokenExpired(jwt({ sub: 'no-exp' })), false);
  assert.equal(VbwdTheme.isTokenExpired('not-a-jwt'), false);
});

test('an expired token is purged on load and the page resolves to anonymous', () => {
  const { storage, document } = loadRuntime({
    storageEntries: SESSION_ENTRIES(EXPIRED_TOKEN),
    bodyAttributes: { 'data-auth': 'pending' },
  });

  assert.deepEqual(storage.keys(), ['vbwd_cart']);
  assert.equal(document.body.getAttribute('data-auth'), 'anonymous');
});

test('an expired token on a public page never fetches regions and never redirects', async () => {
  const fetchStub = createFetchStub();
  const region = createElement({ 'data-vbwd-region': 'r1' });
  const { VbwdTheme, location, storage, document } = loadRuntime({ elements: [region] });
  storage.setItem('auth_token', EXPIRED_TOKEN);

  const swapped = await VbwdTheme.refreshRegions(document, storage, location, fetchStub, null);

  assert.equal(swapped, false);
  assert.equal(fetchStub.calls.length, 0);
  assert.deepEqual(location.assignedUrls, []);
  assert.equal(storage.getItem('auth_token'), null);
});

test('a live token still refreshes the regions', async () => {
  const fetchStub = createFetchStub();
  const region = createElement({ 'data-vbwd-region': 'r1' });
  const { VbwdTheme, location, storage, document } = loadRuntime({ elements: [region] });
  storage.setItem('auth_token', LIVE_TOKEN);

  await VbwdTheme.refreshRegions(document, storage, location, fetchStub, null);

  assert.equal(fetchStub.calls.length, 1);
});

// ── page guards (router guard) ───────────────────────────────────────────────

test('a guest-only page (/login) sends a live session to /dashboard before showing', () => {
  const { location, document } = loadRuntime({
    storageEntries: SESSION_ENTRIES(LIVE_TOKEN),
    pathAndQuery: '/login?redirect=/shop',
    bodyAttributes: { 'data-auth': 'pending', 'data-vbwd-guest-only': '' },
  });

  assert.deepEqual(location.replacedUrls, ['/dashboard']);
  assert.equal(document.body.getAttribute('data-auth'), 'pending');
});

test('a guest-only page with an expired token purges it and shows the form', () => {
  const { location, document, storage } = loadRuntime({
    storageEntries: SESSION_ENTRIES(EXPIRED_TOKEN),
    pathAndQuery: '/login',
    bodyAttributes: { 'data-auth': 'pending', 'data-vbwd-guest-only': '' },
  });

  assert.deepEqual(location.replacedUrls, []);
  assert.deepEqual(location.assignedUrls, []);
  assert.equal(storage.getItem('auth_token'), null);
  assert.equal(document.body.getAttribute('data-auth'), 'anonymous');
});

test('an auth-required page without a live session goes to /login?redirect=', () => {
  const { location } = loadRuntime({
    pathAndQuery: '/pay/stripe?invoice=inv-1',
    bodyAttributes: { 'data-auth': 'pending', 'data-vbwd-auth-required': '' },
  });

  assert.deepEqual(location.assignedUrls, [
    '/login?redirect=' + encodeURIComponent('/pay/stripe?invoice=inv-1'),
  ]);
});

test('an auth-required page with a live session stays and resolves to user', () => {
  const { location, document } = loadRuntime({
    storageEntries: SESSION_ENTRIES(LIVE_TOKEN),
    pathAndQuery: '/pay/stripe?invoice=inv-1',
    bodyAttributes: { 'data-auth': 'pending', 'data-vbwd-auth-required': '' },
  });

  assert.deepEqual(location.assignedUrls, []);
  assert.equal(document.body.getAttribute('data-auth'), 'user');
});

// ── session directive (Login.vue / EmailBlock.vue) ───────────────────────────

function sessionElement(payload) {
  return createElement({ 'data-vbwd-session': '' }, { textContent: JSON.stringify(payload) });
}

test('a login session directive writes the Login.vue keys and goes to its redirect', () => {
  const directive = sessionElement({
    token: LIVE_TOKEN,
    user_id: 'u-9',
    user_permissions: ['shop.*'],
    redirect: '/shop/cart',
  });
  const { storage, location } = loadRuntime({ elements: [directive] });

  assert.equal(storage.getItem('auth_token'), LIVE_TOKEN);
  assert.equal(storage.getItem('user_id'), 'u-9');
  assert.equal(storage.getItem('user_permissions'), '["shop.*"]');
  assert.equal(storage.getItem('user_email'), null);
  assert.deepEqual(location.assignedUrls, ['/shop/cart']);
  assert.equal(directive.removed, true);
});

for (const [stored, expected] of [
  ['/booking/room-1', '/booking/room-1'],
  ['/login?redirect=/x', '/dashboard'],
  ['https://evil.example', '/dashboard'],
  ['//evil.example', '/dashboard'],
  [null, '/dashboard'],
]) {
  test(`a null redirect falls back to redirect_after_login ${stored} → ${expected}`, () => {
    const directive = sessionElement({ token: LIVE_TOKEN, user_id: 'u', redirect: null });
    const sessionEntries = stored === null ? {} : { redirect_after_login: stored };
    const { location, sessionStorage } = loadRuntime({ elements: [directive], sessionEntries });

    assert.deepEqual(location.assignedUrls, [expected]);
    assert.equal(sessionStorage.getItem('redirect_after_login'), null);
  });
}

test('an inline (checkout) session directive writes the EmailBlock keys and announces it', () => {
  const directive = sessionElement({
    token: LIVE_TOKEN,
    user_id: 'u-3',
    user_email: 'buyer@example.com',
  });
  const { storage, location, document } = loadRuntime({ elements: [directive] });

  assert.equal(storage.getItem('auth_token'), LIVE_TOKEN);
  assert.equal(storage.getItem('user_id'), 'u-3');
  assert.equal(storage.getItem('user_email'), 'buyer@example.com');
  assert.equal(storage.getItem('user_permissions'), null);
  assert.deepEqual(location.assignedUrls, []);
  assert.deepEqual(
    plain(document.dispatched.filter((event) => event.target === 'body').map((event) => event.type)),
    ['vbwd:session-started'],
  );
});

test('directives inside swapped htmx content are applied after the swap', () => {
  const { storage, document } = loadRuntime();
  const directive = sessionElement({ token: LIVE_TOKEN, user_id: 'u-4', user_email: 'a@b.c' });
  document.elements.push(directive);

  document.dispatchEvent({ type: 'htmx:afterSwap', detail: {} });

  assert.equal(storage.getItem('user_id'), 'u-4');
  assert.equal(directive.removed, true);
});

// ── cart directives (draftCheckout.ts, CheckoutConfirmationView.vue) ─────────

test('a cart-write directive replaces the cart in the fe-core shape, once', () => {
  const items = [{ type: 'PLAN', id: 'p-1', name: 'Pro Plan', price: 19, quantity: 1, metadata: {} }];
  const directive = createElement(
    { 'data-vbwd-cart-write': 'vbwd_cart' },
    { textContent: JSON.stringify(items) },
  );
  const { storage, document } = loadRuntime({
    storageEntries: { vbwd_cart: '[{"type":"OLD","id":"x","name":"x","price":1,"quantity":1}]' },
    elements: [directive],
  });

  assert.equal(storage.getItem('vbwd_cart'), JSON.stringify(items));
  assert.equal(directive.removed, true);
  assert.ok(document.dispatched.some((event) => event.type === 'vbwd:cart-changed'));
});

test('a cart-clear directive removes that cart only', () => {
  const directive = createElement({ 'data-vbwd-cart-clear': 'vbwd_shop_cart' });
  const { storage } = loadRuntime({
    storageEntries: { vbwd_cart: '[]', vbwd_shop_cart: '[{"productId":"m"}]' },
    elements: [directive],
  });

  assert.deepEqual(storage.keys(), ['vbwd_cart']);
});

test('a cart directive naming a non-cart key is refused', () => {
  const directive = createElement({ 'data-vbwd-cart-write': 'auth_token' }, { textContent: '[]' });

  assert.throws(() => loadRuntime({ storageEntries: { auth_token: LIVE_TOKEN }, elements: [directive] }));
});

// ── cart posting + logout ────────────────────────────────────────────────────

test('a request from inside [data-vbwd-cart] carries that cart as the `cart` parameter', () => {
  const holder = createElement({ 'data-vbwd-cart': 'vbwd_cart' });
  const button = createElement({}, { parent: holder });
  const items = [{ type: 'TOKEN_BUNDLE', id: 'b', name: 'B', price: 5, quantity: 2 }];
  const { document } = loadRuntime({ storageEntries: { vbwd_cart: JSON.stringify(items) } });
  const detail = { path: '/_render/_fragment/checkout/form', headers: {}, parameters: {}, elt: button };

  document.dispatchEvent({ type: 'htmx:configRequest', detail });

  assert.equal(detail.parameters.cart, JSON.stringify(items));
});

test('a request outside any [data-vbwd-cart] carries no cart', () => {
  const { document } = loadRuntime({ storageEntries: { vbwd_cart: '[]' } });
  const detail = { path: '/_render/_fragment/x', headers: {}, parameters: {}, elt: createElement() };

  document.dispatchEvent({ type: 'htmx:configRequest', detail });

  assert.equal(detail.parameters.cart, undefined);
});

test('a [data-vbwd-logout] click ends the session in place and announces it', () => {
  const { document, storage, location } = loadRuntime({ storageEntries: SESSION_ENTRIES(LIVE_TOKEN) });
  const button = createElement({ 'data-vbwd-logout': '' });

  document.dispatchEvent({ type: 'click', target: button });

  assert.deepEqual(storage.keys(), ['vbwd_cart']);
  assert.deepEqual(location.assignedUrls, []);
  assert.ok(document.dispatched.some((event) => event.target === 'body' && event.type === 'vbwd:session-ended'));
});
