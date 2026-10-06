// S152-03 — vbwd-theme.js runtime (D2 + D4), run with `node --test plugins/theme/tests/js/`.
// The script is loaded into a vm context with stub browser globals, exactly as a
// browser would execute it, so the IIFE's wiring is exercised as well as its logic.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

import {
  CORE_CART_ITEMS,
  SHOP_CART_ITEMS,
  SPA_SESSION_KEYS,
  SPA_STORAGE_KEYS,
} from './fixtures/spa_storage_contract.mjs';

const RUNTIME_SCRIPT_PATH = fileURLToPath(
  new URL('../../theme/themes/basic/static/_shared/js/vbwd-theme.js', import.meta.url),
);
const SITE_ORIGIN = 'https://shop.example';
const TOKEN = 'header.payload.signature';

function createStorage(initialEntries = {}) {
  const entries = new Map(Object.entries(initialEntries));
  return {
    getItem: (key) => (entries.has(key) ? entries.get(key) : null),
    setItem: (key, value) => entries.set(key, String(value)),
    removeItem: (key) => entries.delete(key),
    keys: () => [...entries.keys()].sort(),
  };
}

function createRegionElement(regionId, innerHTML) {
  return {
    innerHTML,
    getAttribute: (name) => (name === 'data-vbwd-region' ? regionId : null),
  };
}

function createDocument(bodyDataAuth, { regionElements = [], readyState = 'complete' } = {}) {
  const listenersByType = {};
  const bodyAttributes = new Map();
  if (bodyDataAuth !== undefined) bodyAttributes.set('data-auth', bodyDataAuth);
  const cookieWrites = [];
  return {
    readyState,
    regionElements,
    cookieWrites,
    set cookie(value) {
      cookieWrites.push(value);
    },
    get cookie() {
      return cookieWrites.join('; ');
    },
    querySelectorAll: (selector) => (selector === '[data-vbwd-region]' ? regionElements : []),
    addEventListener(type, listener) {
      (listenersByType[type] = listenersByType[type] || []).push(listener);
    },
    dispatchEvent(event) {
      (listenersByType[event.type] || []).forEach((listener) => listener(event));
      return true;
    },
    body: {
      getAttribute: (name) => (bodyAttributes.has(name) ? bodyAttributes.get(name) : null),
      setAttribute: (name, value) => bodyAttributes.set(name, String(value)),
    },
  };
}

function createLocation(pathAndQuery = '/') {
  const url = new URL(pathAndQuery, SITE_ORIGIN);
  return {
    origin: url.origin,
    href: url.href,
    pathname: url.pathname,
    search: url.search,
    assignedUrls: [],
    assign(target) {
      this.assignedUrls.push(target);
    },
  };
}

function createFetchStub(status, payload) {
  const calls = [];
  const fetchStub = (url, options) => {
    calls.push({ url, options });
    return Promise.resolve({
      status,
      ok: status >= 200 && status < 300,
      json: () => Promise.resolve(payload),
    });
  };
  fetchStub.calls = calls;
  return fetchStub;
}

function createHtmxStub() {
  const processed = [];
  return { processed, process: (element) => processed.push(element) };
}

function loadRuntime({
  storageEntries = {},
  pathAndQuery = '/',
  bodyDataAuth,
  regionElements = [],
  readyState = 'complete',
  fetchStub,
} = {}) {
  const storage = createStorage(storageEntries);
  const document = createDocument(bodyDataAuth, { regionElements, readyState });
  const location = createLocation(pathAndQuery);
  const context = { document, localStorage: storage, location, URL, CustomEvent, Promise };
  if (fetchStub) context.fetch = fetchStub;
  context.window = context;
  vm.createContext(context);
  vm.runInContext(readFileSync(RUNTIME_SCRIPT_PATH, 'utf8'), context, {
    filename: 'vbwd-theme.js',
  });
  return { VbwdTheme: context.VbwdTheme, storage, document, location };
}

// Objects from the vm realm carry that realm's prototypes; compare their data.
const plain = (value) => JSON.parse(JSON.stringify(value));

function configRequest(document, requestPath) {
  const detail = { path: requestPath, headers: {} };
  document.dispatchEvent({ type: 'htmx:configRequest', detail });
  return detail.headers;
}

test('the storage keys constant equals the SPA contract', () => {
  const { VbwdTheme } = loadRuntime();

  assert.deepEqual(plain(VbwdTheme.STORAGE_KEYS), SPA_STORAGE_KEYS);
  assert.deepEqual(plain(VbwdTheme.SESSION_KEYS), SPA_SESSION_KEYS);
  assert.ok(Object.isFrozen(VbwdTheme.STORAGE_KEYS));
});

test('the bearer token is added to same-origin /_render/ requests', () => {
  const { document } = loadRuntime({ storageEntries: { auth_token: TOKEN } });

  for (const requestPath of [
    '/_render/_fragment/regions?path=%2Fshop',
    `${SITE_ORIGIN}/_render/_fragment/regions`,
  ]) {
    assert.equal(configRequest(document, requestPath).Authorization, `Bearer ${TOKEN}`);
  }
});

test('the bearer token is never added to other paths or other origins', () => {
  const { document } = loadRuntime({ storageEntries: { auth_token: TOKEN } });

  for (const requestPath of [
    '/api/v1/user/profile',
    '/_renderer/x',
    '/shop/_render/x',
    'https://evil.example/_render/_fragment/regions',
    '//evil.example/_render/_fragment/regions',
    'http://shop.example/_render/_fragment/regions',
  ]) {
    assert.equal(configRequest(document, requestPath).Authorization, undefined, requestPath);
  }
});

test('no token means no Authorization header', () => {
  const { document } = loadRuntime();

  assert.equal(configRequest(document, '/_render/_fragment/regions').Authorization, undefined);
});

test('a 401 clears the session keys, keeps the carts and redirects to /login', () => {
  const storageEntries = {
    auth_token: TOKEN,
    user: '{"id":"u1"}',
    user_id: 'u1',
    user_permissions: '["*"]',
    vbwd_cart: JSON.stringify(CORE_CART_ITEMS),
    vbwd_shop_cart: JSON.stringify(SHOP_CART_ITEMS),
  };
  const { document, storage, location } = loadRuntime({
    storageEntries,
    pathAndQuery: '/shop/cart?coupon=a b&step=2',
  });

  document.dispatchEvent({ type: 'htmx:responseError', detail: { xhr: { status: 401 } } });

  assert.deepEqual(storage.keys(), ['vbwd_cart', 'vbwd_shop_cart']);
  assert.equal(storage.getItem('vbwd_cart'), storageEntries.vbwd_cart);
  assert.deepEqual(location.assignedUrls, [
    '/login?redirect=' + encodeURIComponent('/shop/cart?coupon=a%20b&step=2'),
  ]);
  assert.equal(location.assignedUrls[0], '/login?redirect=%2Fshop%2Fcart%3Fcoupon%3Da%2520b%26step%3D2');
});

test('a non-401 error leaves the session alone', () => {
  const { document, storage, location } = loadRuntime({ storageEntries: { auth_token: TOKEN } });

  document.dispatchEvent({ type: 'htmx:responseError', detail: { xhr: { status: 500 } } });

  assert.equal(storage.getItem('auth_token'), TOKEN);
  assert.deepEqual(location.assignedUrls, []);
});

test('data-auth pending becomes user when a token exists', () => {
  const { document } = loadRuntime({ storageEntries: { auth_token: TOKEN }, bodyDataAuth: 'pending' });

  assert.equal(document.body.getAttribute('data-auth'), 'user');
});

test('data-auth pending becomes anonymous without a token', () => {
  const { document } = loadRuntime({ bodyDataAuth: 'pending' });

  assert.equal(document.body.getAttribute('data-auth'), 'anonymous');
});

test('a page that is not pending keeps its body untouched', () => {
  const { document } = loadRuntime({ storageEntries: { auth_token: TOKEN } });

  assert.equal(document.body.getAttribute('data-auth'), null);
});

test('cart writes use the exact fe-core and shop serialized shape', () => {
  const { VbwdTheme, storage, document } = loadRuntime();

  VbwdTheme.writeCart(storage, document, SPA_STORAGE_KEYS.cart, CORE_CART_ITEMS);
  VbwdTheme.writeCart(storage, document, SPA_STORAGE_KEYS.shopCart, SHOP_CART_ITEMS);

  assert.equal(storage.getItem('vbwd_cart'), JSON.stringify(CORE_CART_ITEMS));
  assert.equal(storage.getItem('vbwd_shop_cart'), JSON.stringify(SHOP_CART_ITEMS));
  assert.deepEqual(plain(VbwdTheme.readCart(storage, 'vbwd_cart')), CORE_CART_ITEMS);
  assert.deepEqual(plain(VbwdTheme.readCart(storage, 'vbwd_shop_cart')), SHOP_CART_ITEMS);
});

test('reading a missing or corrupt cart gives an empty list, like the SPA stores', () => {
  const { VbwdTheme } = loadRuntime();
  const storage = createStorage({ vbwd_shop_cart: '{not json' });

  assert.deepEqual(plain(VbwdTheme.readCart(storage, 'vbwd_cart')), []);
  assert.deepEqual(plain(VbwdTheme.readCart(storage, 'vbwd_shop_cart')), []);
});

test('a cart write dispatches vbwd:cart-changed with the key and items', () => {
  const { VbwdTheme, storage, document } = loadRuntime();
  const receivedEvents = [];
  document.addEventListener('vbwd:cart-changed', (event) => receivedEvents.push(event));

  VbwdTheme.writeCart(storage, document, 'vbwd_shop_cart', SHOP_CART_ITEMS);

  assert.equal(receivedEvents.length, 1);
  assert.equal(VbwdTheme.CART_CHANGED_EVENT, 'vbwd:cart-changed');
  assert.deepEqual(plain(receivedEvents[0].detail), { key: 'vbwd_shop_cart', items: SHOP_CART_ITEMS });
});

test('cart helpers refuse keys that are not cart keys', () => {
  const { VbwdTheme, storage, document } = loadRuntime();

  assert.throws(() => VbwdTheme.writeCart(storage, document, 'auth_token', []));
  assert.throws(() => VbwdTheme.readCart(storage, 'user'));
  assert.equal(storage.getItem('auth_token'), null);
});

// S152-04 / D12 — personalised regions are swapped in after an anonymous page load.

const REGIONS_PAYLOAD = { regions: { r1: 'GATED-PRO', r2: 'Hello ada' } };

function regionSetup(overrides = {}) {
  const regionElements = [
    createRegionElement('r1', 'PUBLIC-TEASER'),
    createRegionElement('r2', 'Sign in'),
  ];
  const fetchStub = createFetchStub(overrides.status || 200, overrides.payload || REGIONS_PAYLOAD);
  const runtime = loadRuntime({
    storageEntries: overrides.storageEntries || { auth_token: TOKEN, user_id: 'ada' },
    pathAndQuery: '/shop/product/mug?colour=red',
    regionElements: overrides.regionElements || regionElements,
    // The install-time refresh must not succeed, so each test drives refreshRegions itself.
    fetchStub: createFetchStub(503, {}),
  });
  return { ...runtime, regionElements: overrides.regionElements || regionElements, fetchStub };
}

test('regions are fetched for the current path with the bearer and swapped in', async () => {
  const { VbwdTheme, document, storage, location, regionElements, fetchStub } = regionSetup();
  const htmx = createHtmxStub();

  const swapped = await VbwdTheme.refreshRegions(document, storage, location, fetchStub, htmx);

  assert.equal(swapped, true);
  assert.equal(fetchStub.calls.length, 1);
  assert.equal(
    fetchStub.calls[0].url,
    '/_render/_fragment/regions?path=' + encodeURIComponent('/shop/product/mug?colour=red'),
  );
  assert.equal(fetchStub.calls[0].options.headers.Authorization, `Bearer ${TOKEN}`);
  assert.deepEqual(regionElements.map((element) => element.innerHTML), ['GATED-PRO', 'Hello ada']);
  assert.deepEqual(htmx.processed, regionElements);
  assert.equal(document.body.getAttribute('data-auth'), 'user');
});

test('a swap announces vbwd:regions-swapped so adapter runtimes re-apply client state', async () => {
  const { VbwdTheme, document, storage, location, regionElements, fetchStub } = regionSetup();
  const announced = [];
  document.addEventListener('vbwd:regions-swapped', (event) => announced.push(event.detail));

  await VbwdTheme.refreshRegions(document, storage, location, fetchStub, undefined);

  assert.equal(announced.length, 1);
  assert.equal(announced[0].regions.length, regionElements.length);
  announced[0].regions.forEach((element, index) => assert.equal(element, regionElements[index]));
});

test('no swap means no vbwd:regions-swapped event', async () => {
  const { VbwdTheme, document, storage, location } = regionSetup();
  const announced = [];
  document.addEventListener('vbwd:regions-swapped', () => announced.push(true));

  await VbwdTheme.refreshRegions(document, storage, location, createFetchStub(500, {}), undefined);

  assert.equal(announced.length, 0);
});

test('a region missing from the response is left as rendered', async () => {
  const { VbwdTheme, document, storage, location, regionElements, fetchStub } = regionSetup({
    payload: { regions: { r2: 'Hello ada' } },
  });

  await VbwdTheme.refreshRegions(document, storage, location, fetchStub, undefined);

  assert.deepEqual(regionElements.map((element) => element.innerHTML), ['PUBLIC-TEASER', 'Hello ada']);
});

test('without a token no regions request is made', async () => {
  const { VbwdTheme, document, storage, location, regionElements, fetchStub } = regionSetup({
    storageEntries: {},
  });

  assert.equal(await VbwdTheme.refreshRegions(document, storage, location, fetchStub), false);
  assert.equal(fetchStub.calls.length, 0);
  assert.equal(regionElements[0].innerHTML, 'PUBLIC-TEASER');
});

test('a page without regions makes no request', async () => {
  const { VbwdTheme, document, storage, location, fetchStub } = regionSetup({ regionElements: [] });

  assert.equal(await VbwdTheme.refreshRegions(document, storage, location, fetchStub), false);
  assert.equal(fetchStub.calls.length, 0);
});

test('a 401 from the regions endpoint ends the session and redirects to /login', async () => {
  const { VbwdTheme, document, storage, location, regionElements, fetchStub } = regionSetup({
    status: 401,
    storageEntries: { auth_token: TOKEN, user_id: 'ada', vbwd_cart: '[]' },
  });

  assert.equal(await VbwdTheme.refreshRegions(document, storage, location, fetchStub), false);
  assert.deepEqual(storage.keys(), ['vbwd_cart']);
  assert.deepEqual(location.assignedUrls, [
    '/login?redirect=' + encodeURIComponent('/shop/product/mug?colour=red'),
  ]);
  assert.equal(regionElements[0].innerHTML, 'PUBLIC-TEASER');
});

test('another error status keeps the anonymous regions and the session', async () => {
  const { VbwdTheme, document, storage, location, regionElements, fetchStub } = regionSetup({
    status: 500,
  });

  assert.equal(await VbwdTheme.refreshRegions(document, storage, location, fetchStub), false);
  assert.equal(storage.getItem('auth_token'), TOKEN);
  assert.equal(regionElements[0].innerHTML, 'PUBLIC-TEASER');
  assert.notEqual(document.body.getAttribute('data-auth'), 'user');
});

test('a network failure keeps the anonymous regions', async () => {
  const { VbwdTheme, document, storage, location, regionElements } = regionSetup();
  const failingFetch = () => Promise.reject(new Error('offline'));

  assert.equal(await VbwdTheme.refreshRegions(document, storage, location, failingFetch), false);
  assert.equal(regionElements[0].innerHTML, 'PUBLIC-TEASER');
});

test('on DOMContentLoaded the installed runtime refreshes the regions', async () => {
  const regionElements = [createRegionElement('r1', 'PUBLIC-TEASER')];
  const fetchStub = createFetchStub(200, { regions: { r1: 'GATED-PRO' } });
  const { document } = loadRuntime({
    storageEntries: { auth_token: TOKEN },
    regionElements,
    readyState: 'loading',
    fetchStub,
  });
  assert.equal(fetchStub.calls.length, 0);

  document.dispatchEvent({ type: 'DOMContentLoaded' });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(fetchStub.calls.length, 1);
  assert.equal(regionElements[0].innerHTML, 'GATED-PRO');
});

// ── S152-05 language switcher (D13): `vbwd_lang` is the cookie the CMS routing rules read.

const LANGUAGE_COOKIE_ATTRIBUTES = '; path=/; max-age=31536000; SameSite=Lax';

function createLanguageLink(language) {
  return {
    getAttribute: (name) => (name === 'data-vbwd-language' ? language : null),
  };
}

function clickEvent(closestResult) {
  return {
    type: 'click',
    defaultPrevented: false,
    target: { closest: (selector) => (selector === '[data-vbwd-language]' ? closestResult : null) },
    preventDefault() {
      this.defaultPrevented = true;
    },
  };
}

test('setLanguage writes the vbwd_lang cookie for the whole site for a year', () => {
  const { VbwdTheme, document } = loadRuntime();

  VbwdTheme.setLanguage('de');

  assert.deepEqual(document.cookieWrites, ['vbwd_lang=de' + LANGUAGE_COOKIE_ATTRIBUTES]);
});

test('setLanguage encodes the value so it cannot add cookie attributes', () => {
  const { VbwdTheme, document } = loadRuntime();

  VbwdTheme.setLanguage('de; domain=evil.example');

  assert.deepEqual(document.cookieWrites, [
    'vbwd_lang=de%3B%20domain%3Devil.example' + LANGUAGE_COOKIE_ATTRIBUTES,
  ]);
});

test('a click on a language switch link sets the cookie and still navigates', () => {
  const { document } = loadRuntime();
  const event = clickEvent(createLanguageLink('fr'));

  document.dispatchEvent(event);

  assert.deepEqual(document.cookieWrites, ['vbwd_lang=fr' + LANGUAGE_COOKIE_ATTRIBUTES]);
  assert.equal(event.defaultPrevented, false);
});

test('a click elsewhere sets no cookie', () => {
  const { document } = loadRuntime();

  document.dispatchEvent(clickEvent(null));
  document.dispatchEvent({ type: 'click', target: {} });

  assert.deepEqual(document.cookieWrites, []);
});
