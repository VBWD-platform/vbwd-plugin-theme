/*
 * vbwd-theme.js — the themed pages' browser runtime (S152 D2 + D4). No build step, ES2019.
 *
 * Owns exactly the SPA's localStorage keys, so a session or cart started on either
 * renderer carries over to the other:
 *   - adds `Authorization: Bearer <auth_token>` to same-origin htmx requests under /_render/;
 *   - on a 401 clears the session keys (never the carts) and goes to /login?redirect=…;
 *   - resolves <body data-auth="pending"> to "user" or "anonymous";
 *   - reads/writes the carts in the SPA stores' JSON shape and fires `vbwd:cart-changed`;
 *   - on DOMContentLoaded, with a token, swaps each [data-vbwd-region] for the viewer's
 *     version from /_render/_fragment/regions (S152 D12), marks <body data-auth="user"> and
 *     fires `vbwd:regions-swapped` so adapter runtimes re-apply client-only state;
 *   - a click on a [data-vbwd-language] switch link stores that language in the `vbwd_lang`
 *     cookie the CMS routing rules read (S152 D13), then the link navigates as usual;
 *   - an expired JWT counts as no session and is purged, like the SPA's isAuthenticated()
 *     (S152-07): public pages never bounce to /login on a stale token;
 *   - <body data-vbwd-guest-only> (/login) sends a live session to /dashboard and
 *     <body data-vbwd-auth-required> (/pay/*) sends a missing one to /login?redirect= —
 *     the SPA router guard;
 *   - server directives in the page or in swapped content: [data-vbwd-session] (JSON) stores
 *     the session keys, then follows its `redirect` (login) or fires vbwd:session-started on
 *     <body> (inline checkout login); [data-vbwd-cart-write="<cart key>"] (JSON items)
 *     replaces a cart; [data-vbwd-cart-clear="<cart key>"] removes one;
 *   - a request from inside [data-vbwd-cart="<cart key>"] carries that cart as `cart`;
 *   - a [data-vbwd-logout] click clears the session in place and fires vbwd:session-ended.
 *
 * Every function takes its storage / location / document explicitly; only the IIFE's
 * last lines touch the real browser globals. Exposed as window.VbwdTheme.
 */
(function (window) {
  'use strict';

  var STORAGE_KEYS = Object.freeze({
    authToken: 'auth_token',
    user: 'user',
    userId: 'user_id',
    userPermissions: 'user_permissions',
    cart: 'vbwd_cart',
    shopCart: 'vbwd_shop_cart'
  });
  var SESSION_KEYS = Object.freeze([
    STORAGE_KEYS.authToken,
    STORAGE_KEYS.user,
    STORAGE_KEYS.userId,
    STORAGE_KEYS.userPermissions
  ]);
  var CART_KEYS = Object.freeze([STORAGE_KEYS.cart, STORAGE_KEYS.shopCart]);
  var CART_CHANGED_EVENT = 'vbwd:cart-changed';
  var RENDER_PATH_PREFIX = '/_render/';
  var LOGIN_PATH = '/login';
  var UNAUTHORIZED_STATUS = 401;
  var AUTH_ATTRIBUTE = 'data-auth';
  var AUTH_PENDING = 'pending';
  var AUTH_USER = 'user';
  var AUTH_ANONYMOUS = 'anonymous';
  var REGIONS_ENDPOINT = '/_render/_fragment/regions';
  var REGION_SELECTOR = '[data-vbwd-region]';
  var REGION_ATTRIBUTE = 'data-vbwd-region';
  var REGIONS_SWAPPED_EVENT = 'vbwd:regions-swapped';
  var LANGUAGE_COOKIE_NAME = 'vbwd_lang';
  var LANGUAGE_COOKIE_ATTRIBUTES = '; path=/; max-age=31536000; SameSite=Lax';
  var LANGUAGE_SWITCH_SELECTOR = '[data-vbwd-language]';
  var LANGUAGE_SWITCH_ATTRIBUTE = 'data-vbwd-language';
  var DASHBOARD_PATH = '/dashboard';
  var GUEST_ONLY_ATTRIBUTE = 'data-vbwd-guest-only';
  var AUTH_REQUIRED_ATTRIBUTE = 'data-vbwd-auth-required';
  var REDIRECT_AFTER_LOGIN_KEY = 'redirect_after_login';
  var USER_EMAIL_KEY = 'user_email';
  var SESSION_DIRECTIVE_SELECTOR = '[data-vbwd-session]';
  var CART_WRITE_ATTRIBUTE = 'data-vbwd-cart-write';
  var CART_CLEAR_ATTRIBUTE = 'data-vbwd-cart-clear';
  var CART_HOLDER_ATTRIBUTE = 'data-vbwd-cart';
  var CART_PARAMETER = 'cart';
  var LOGOUT_SELECTOR = '[data-vbwd-logout]';
  var SESSION_STARTED_EVENT = 'vbwd:session-started';
  var SESSION_ENDED_EVENT = 'vbwd:session-ended';
  var MILLISECONDS_PER_SECOND = 1000;

  // token.ts decodeJwtExp: the `exp` claim of a 3-part JWT, else null.
  function decodeJwtExp(token) {
    var parts = String(token || '').split('.');
    if (parts.length !== 3) {
      return null;
    }
    try {
      var payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
      return typeof payload.exp === 'number' ? payload.exp : null;
    } catch (decodeError) {
      return null;
    }
  }

  // token.ts isTokenExpired: only a provable past `exp` is expired.
  function isTokenExpired(token) {
    var expiry = decodeJwtExp(token);
    return expiry !== null && expiry * MILLISECONDS_PER_SECOND <= Date.now();
  }

  function clearSession(storage) {
    SESSION_KEYS.forEach(function (key) {
      storage.removeItem(key);
    });
  }

  // api/index.ts isAuthenticated: a token that is present and not provably expired;
  // an expired one is purged on the spot.
  function hasLiveSession(storage) {
    var token = storage.getItem(STORAGE_KEYS.authToken);
    if (!token) {
      return false;
    }
    if (isTokenExpired(token)) {
      clearSession(storage);
      return false;
    }
    return true;
  }

  function isSameOriginRenderRequest(requestPath, location) {
    var target = new URL(requestPath, location.href);
    return target.origin === location.origin && target.pathname.indexOf(RENDER_PATH_PREFIX) === 0;
  }

  function addBearerToken(event, storage, location) {
    var token = storage.getItem(STORAGE_KEYS.authToken);
    if (token && isSameOriginRenderRequest(event.detail.path, location)) {
      event.detail.headers.Authorization = 'Bearer ' + token;
    }
  }

  function addCartParameter(event, storage) {
    var element = event.detail.elt;
    var holder = element && element.closest ? element.closest('[' + CART_HOLDER_ATTRIBUTE + ']') : null;
    if (holder && event.detail.parameters) {
      var cartKey = holder.getAttribute(CART_HOLDER_ATTRIBUTE);
      event.detail.parameters[CART_PARAMETER] = JSON.stringify(readCart(storage, cartKey));
    }
  }

  function endSession(storage, location) {
    clearSession(storage);
    var currentPathAndQuery = location.pathname + location.search;
    location.assign(LOGIN_PATH + '?redirect=' + encodeURIComponent(currentPathAndQuery));
  }

  function handleResponseError(event, storage, location) {
    if (event.detail.xhr.status === UNAUTHORIZED_STATUS) {
      endSession(storage, location);
    }
  }

  function confirmSession(document, storage) {
    var body = document.body;
    if (body.getAttribute(AUTH_ATTRIBUTE) !== AUTH_PENDING) {
      return;
    }
    body.setAttribute(AUTH_ATTRIBUTE, hasLiveSession(storage) ? AUTH_USER : AUTH_ANONYMOUS);
  }

  function swapRegions(regionElements, regionsById, htmx) {
    regionElements.forEach(function (element) {
      var regionId = element.getAttribute(REGION_ATTRIBUTE);
      if (!Object.prototype.hasOwnProperty.call(regionsById, regionId)) {
        return;
      }
      element.innerHTML = regionsById[regionId];
      if (htmx) {
        htmx.process(element);
      }
    });
  }

  // Resolves true when the viewer's regions were swapped in; false otherwise (the
  // anonymous regions stay). A 401 ends the session, exactly like a fragment 401.
  function refreshRegions(document, storage, location, fetchFunction, htmx) {
    var regionElements = Array.prototype.slice.call(document.querySelectorAll(REGION_SELECTOR));
    if (!hasLiveSession(storage) || regionElements.length === 0) {
      return Promise.resolve(false);
    }
    var token = storage.getItem(STORAGE_KEYS.authToken);
    var regionsUrl = REGIONS_ENDPOINT + '?path=' + encodeURIComponent(location.pathname + location.search);
    var requestOptions = {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/json' },
      credentials: 'same-origin'
    };
    return fetchFunction(regionsUrl, requestOptions)
      .then(function (response) {
        if (response.status === UNAUTHORIZED_STATUS) {
          endSession(storage, location);
          return false;
        }
        if (!response.ok) {
          return false;
        }
        return response.json().then(function (payload) {
          swapRegions(regionElements, payload.regions || {}, htmx);
          document.body.setAttribute(AUTH_ATTRIBUTE, AUTH_USER);
          // Swapped markup is server state again: adapter runtimes re-apply client state.
          document.dispatchEvent(
            new CustomEvent(REGIONS_SWAPPED_EVENT, { detail: { regions: regionElements } })
          );
          return true;
        });
      })
      .catch(function () {
        return false;
      });
  }

  function whenDocumentReady(document, callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback);
    } else {
      callback();
    }
  }

  function assertCartKey(cartKey) {
    if (CART_KEYS.indexOf(cartKey) === -1) {
      throw new Error('vbwd-theme: "' + cartKey + '" is not a cart key');
    }
  }

  // Same as the SPA stores' loadFromStorage: a bare JSON array, [] when absent or corrupt.
  function readCart(storage, cartKey) {
    assertCartKey(cartKey);
    try {
      var items = JSON.parse(storage.getItem(cartKey) || '[]');
      return Array.isArray(items) ? items : [];
    } catch (parseError) {
      return [];
    }
  }

  // Same as the SPA stores' saveToStorage: JSON.stringify(items), nothing wrapped around it.
  function writeCart(storage, document, cartKey, items) {
    assertCartKey(cartKey);
    storage.setItem(cartKey, JSON.stringify(items));
    document.dispatchEvent(
      new CustomEvent(CART_CHANGED_EVENT, { detail: { key: cartKey, items: items } })
    );
  }

  function writeLanguageCookie(document, language) {
    document.cookie =
      LANGUAGE_COOKIE_NAME + '=' + encodeURIComponent(language) + LANGUAGE_COOKIE_ATTRIBUTES;
  }

  function handleLanguageSwitchClick(event, document) {
    var target = event.target;
    var languageSwitch = target && target.closest ? target.closest(LANGUAGE_SWITCH_SELECTOR) : null;
    if (languageSwitch) {
      writeLanguageCookie(document, languageSwitch.getAttribute(LANGUAGE_SWITCH_ATTRIBUTE));
    }
  }

  function isSafeRedirectPath(target) {
    return (
      typeof target === 'string' &&
      target.charAt(0) === '/' &&
      target.indexOf('//') !== 0 &&
      target.indexOf('/\\') !== 0 &&
      target.indexOf(LOGIN_PATH) !== 0
    );
  }

  // Login.vue: ?redirect= (already checked by the server) wins, else the session value
  // redirect_after_login (always consumed), never back into /login, else /dashboard.
  function loginTarget(serverRedirect, sessionStorage) {
    if (serverRedirect) {
      return serverRedirect;
    }
    var stored = sessionStorage.getItem(REDIRECT_AFTER_LOGIN_KEY);
    sessionStorage.removeItem(REDIRECT_AFTER_LOGIN_KEY);
    return isSafeRedirectPath(stored) ? stored : DASHBOARD_PATH;
  }

  function startSession(payload, environment) {
    var storage = environment.storage;
    storage.setItem(STORAGE_KEYS.authToken, payload.token);
    if (payload.user_id) {
      storage.setItem(STORAGE_KEYS.userId, payload.user_id);
    }
    if (Array.isArray(payload.user_permissions)) {
      storage.setItem(STORAGE_KEYS.userPermissions, JSON.stringify(payload.user_permissions));
    }
    if (payload.user_email) {
      storage.setItem(USER_EMAIL_KEY, payload.user_email);
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'redirect')) {
      environment.location.assign(loginTarget(payload.redirect, environment.sessionStorage));
      return;
    }
    environment.document.body.dispatchEvent(new CustomEvent(SESSION_STARTED_EVENT, { bubbles: true }));
  }

  function applyServerDirectives(environment) {
    var document = environment.document;
    Array.prototype.slice.call(document.querySelectorAll(SESSION_DIRECTIVE_SELECTOR)).forEach(function (element) {
      element.remove();
      startSession(JSON.parse(element.textContent), environment);
    });
    Array.prototype.slice.call(document.querySelectorAll('[' + CART_WRITE_ATTRIBUTE + ']')).forEach(function (element) {
      element.remove();
      writeCart(environment.storage, document, element.getAttribute(CART_WRITE_ATTRIBUTE), JSON.parse(element.textContent));
    });
    Array.prototype.slice.call(document.querySelectorAll('[' + CART_CLEAR_ATTRIBUTE + ']')).forEach(function (element) {
      var cartKey = element.getAttribute(CART_CLEAR_ATTRIBUTE);
      element.remove();
      assertCartKey(cartKey);
      environment.storage.removeItem(cartKey);
      document.dispatchEvent(new CustomEvent(CART_CHANGED_EVENT, { detail: { key: cartKey, items: [] } }));
    });
  }

  // The SPA router guard. True when the page is being left (nothing else should run).
  function guardPage(document, storage, location) {
    var body = document.body;
    if (body.getAttribute(GUEST_ONLY_ATTRIBUTE) !== null && hasLiveSession(storage)) {
      location.replace(DASHBOARD_PATH);
      return true;
    }
    if (body.getAttribute(AUTH_REQUIRED_ATTRIBUTE) !== null && !hasLiveSession(storage)) {
      endSession(storage, location);
      return true;
    }
    return false;
  }

  function handleLogoutClick(event, document, storage) {
    var target = event.target;
    if (target && target.closest && target.closest(LOGOUT_SELECTOR)) {
      clearSession(storage);
      document.body.dispatchEvent(new CustomEvent(SESSION_ENDED_EVENT, { bubbles: true }));
    }
  }

  function install(document, storage, location, window) {
    var environment = {
      document: document,
      storage: storage,
      location: location,
      sessionStorage: window.sessionStorage
    };
    document.addEventListener('htmx:configRequest', function (event) {
      addBearerToken(event, storage, location);
      addCartParameter(event, storage);
    });
    document.addEventListener('htmx:afterSwap', function () {
      applyServerDirectives(environment);
    });
    document.addEventListener(REGIONS_SWAPPED_EVENT, function () {
      applyServerDirectives(environment);
    });
    document.addEventListener('htmx:responseError', function (event) {
      handleResponseError(event, storage, location);
    });
    document.addEventListener('click', function (event) {
      handleLanguageSwitchClick(event, document);
      handleLogoutClick(event, document, storage);
    });
    if (guardPage(document, storage, location)) {
      return;
    }
    // Before htmx's own DOMContentLoaded processing, so a hydrated cart is in place
    // when the first `load`-triggered fragment request reads it.
    applyServerDirectives(environment);
    confirmSession(document, storage);
    whenDocumentReady(document, function () {
      if (typeof window.fetch === 'function') {
        refreshRegions(document, storage, location, window.fetch.bind(window), window.htmx);
      }
    });
  }

  window.VbwdTheme = Object.freeze({
    STORAGE_KEYS: STORAGE_KEYS,
    SESSION_KEYS: SESSION_KEYS,
    CART_CHANGED_EVENT: CART_CHANGED_EVENT,
    addBearerToken: addBearerToken,
    handleResponseError: handleResponseError,
    endSession: endSession,
    confirmSession: confirmSession,
    refreshRegions: refreshRegions,
    isTokenExpired: isTokenExpired,
    readCart: readCart,
    writeCart: writeCart,
    setLanguage: function (language) {
      writeLanguageCookie(window.document, language);
    }
  });

  install(window.document, window.localStorage, window.location, window);
})(window);
