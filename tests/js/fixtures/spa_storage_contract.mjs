// The SPA's localStorage contract (S152 D2), copied by hand from the SPA sources.
// DRIFT NOTE: if one of these sources changes a key or the cart item shape, update
// this fixture and vbwd-theme.js together; the runtime tests compare against it.
//
//   auth_token, user_id, user_permissions — vbwd-fe-user/vue/src/api/index.ts
//                                           (initializeApi, clearApiAuth, hasUserPermission)
//   user                                  — vbwd-fe-user/vue/src/layouts/UserLayout.vue
//   vbwd_cart (ICartItem[])               — vbwd-fe-core/src/stores/cart.ts
//                                           (STORAGE_KEY, saveToStorage = JSON.stringify(items))
//   vbwd_shop_cart (CartItem[])           — vbwd-fe-user/plugins/shop/shop/stores/cart.ts
//                                           (STORAGE_KEY, saveToStorage = JSON.stringify(items))

export const SPA_STORAGE_KEYS = {
  authToken: 'auth_token',
  user: 'user',
  userId: 'user_id',
  userPermissions: 'user_permissions',
  cart: 'vbwd_cart',
  shopCart: 'vbwd_shop_cart',
};

// The keys the SPA clears when a session ends (clearApiAuth + UserLayout logout).
// Carts survive a logout.
export const SPA_SESSION_KEYS = ['auth_token', 'user', 'user_id', 'user_permissions'];

// fe-core ICartItem: { type, id, name, price, quantity, metadata? } — a bare array.
export const CORE_CART_ITEMS = [
  {
    type: 'TOKEN_BUNDLE',
    id: 'bundle-1000',
    name: '1000 Tokens',
    price: 10,
    quantity: 2,
    metadata: { tokens: 1000 },
  },
  { type: 'PLAN', id: 'plan-pro', name: 'Pro', price: 29.9, quantity: 1 },
];

// shop CartItem: product fields plus the optional S85.4 pricing split — a bare array.
export const SHOP_CART_ITEMS = [
  {
    productId: 'product-mug',
    productSlug: 'mug',
    productName: 'Mug',
    imageUrl: '/uploads/mug.png',
    price: 12.5,
    currency: 'EUR',
    quantity: 3,
    maxQuantity: 10,
    isDigital: false,
    weight: 0.4,
    variantId: 'variant-blue',
    variantName: 'Blue',
    netAmount: 10.5,
    grossAmount: 12.5,
    taxes: [{ code: 'VAT', rate: '19', amount: 2 }],
    effectiveDisplayMode: 'brutto',
    pricesDisplayMode: 'brutto',
  },
];
