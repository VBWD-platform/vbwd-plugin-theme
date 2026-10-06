# Writing a theme (child theme of `basic`)

A **child theme** is a backend plugin that restyles or re-templates the server-rendered public
pages (`VBWD_FRONTEND_MODE=theme`). It changes presentation only. It never fetches data and never
adds routes; adapters do that (see `writing-a-theme-adapter.md`). The mode, routing and core seams
are in `docs/architecture/frontend-modes.md`.

> **Engineering requirements (BINDING):** TDD-first · DevOps-first · SOLID · DI · DRY ·
> Liskov · clean code · **NO OVERENGINEERING**.

## Layout and registration

```
plugins/theme_acme/
├── __init__.py              # ThemeAcmePlugin(BasePlugin), dependencies=["theme>=1.0"]
├── config.json              # at least debug_mode (every plugin ships both files)
├── admin-config.json
└── theme/
    ├── templates/           # overrides, same relative names as the template they replace
    │   └── cms/page_types/page.html.j2
    ├── static/
    │   ├── _shared/*.css    # every surface
    │   └── public/*.css     # the public surface
    ├── translations/de.json # {"key": "string"} — overrides/extends basic + adapter strings
    └── tokens.json          # {"--vbwd-color-primary": "#0a7f6f"}
```

```python
from pathlib import Path

from vbwd.plugins.base import BasePlugin, PluginMetadata

from plugins.theme.theme.theme_registry import BASIC_THEME_SLUG, ThemeDescriptor, resolve_theme_registry

ACME_DESCRIPTOR = ThemeDescriptor(
    slug="acme", name="Acme", parent=BASIC_THEME_SLUG, root=Path(__file__).resolve().parent / "theme",
)


class ThemeAcmePlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name="theme_acme", version="1.0.0", author="…",
                              description="Acme theme", dependencies=["theme>=1.0"])

    def on_enable(self) -> None:
        theme_registry = resolve_theme_registry()
        if not theme_registry.is_registered(ACME_DESCRIPTOR.slug):
            theme_registry.register(ACME_DESCRIPTOR)
```

**Activating it:**
- Set the operator config of the `theme` plugin to `active_theme: acme`, in the admin UI or with
  `PUT /api/v1/admin/plugins/theme/config`.
- The value is read on **every render**, so switching themes needs no restart.
- An unknown or unregistered slug falls back to `basic` with one warning.
- *Enabling* a theme plugin does need an api restart: plugins register at boot.

**`register()` validates up front**, so a broken theme fails at boot, not on a page:
- the slug matches `[a-z0-9_-]+` and is unique;
- the parent exists, and a theme cannot be its own parent;
- `templates/` exists;
- token names match `^--vbwd-[a-z0-9-]+$`, and token values are strings without `; { } < >`;
- translation files are JSON objects of string → string.

A parent may itself be a child theme (`basic ← acme ← acme_dark`).

## Template resolution (D8)

For an unqualified name the first hit wins:

1. operator overrides: `var/assets/theme/<active>/templates/` (no plugin needed);
2. the active theme, then its parents, up to `basic`;
3. templates contributed by adapters (`theme_cms`, `theme_shop`, …).

`@<slug>/<name>` resolves only inside that theme. That is how a child extends the template it
replaces without recursing into itself:

```jinja
{# theme/templates/_shared/partials/footer.html.j2 #}
{% extends "@basic/_shared/partials/footer.html.j2" %}
```

Adapter templates (rank 3) have no namespace. To change one, override it under the same name and
extend its base, e.g. `cms/page_types/page.html.j2` → `{% extends "cms/page_base.html.j2" %}` and
fill `body_header` (this is exactly what the `theme_demo` fixture does).

## The contract rule: keep every testid and every region

A child may re-arrange anything, but it **must keep**:

- every `data-testid`. The e2e parity suite selects by testid in both modes, and so do
  `vbwd-theme.js` and the DOM-contract tests;
- every `data-vbwd-region` wrapper. Regions are numbered `r1, r2, …` in document order and swapped
  by id after login. Dropping or reordering one breaks the swap;
- the text the parity specs match (`text=Pay with Stripe`, `text=Invoice`, …) and classes they use
  (`.card`).

Each adapter's DOM-contract test renders the **active** chain, so a child theme that drops a testid
fails its own CI. Run the adapter suites with your theme active, see "Testing".

## Access levels, permissions, personalised regions (D12)

```jinja
{% access "subscribed-pro", "subscribed-basic" %}
  <a href="/downloads">Your downloads</a>
{% else %}
  <a href="/pricing" data-testid="upsell">Upgrade</a>
{% endaccess %}

{% permission "booking.manage" %}<a href="/dashboard/booking">Manage</a>{% endpermission %}

{% region %}
  {% if viewer.user_id %}<a href="/dashboard">My account</a>{% else %}<a href="/login">Log in</a>{% endif %}
{% endregion %}
```

- **Anonymous HTML holds only the `else` branch.** The gated markup is never in the bytes, so it is
  never cached or crawled.
- With a token, the runtime re-renders the same page for the viewer
  (`/_render/_fragment/regions`) and swaps the marked regions.
- `access` matches **any** of the level slugs. An unknown slug is simply false.
- `permission` uses fe-user `hasUserPermission` semantics: exact, `prefix.*` and `*`.
- Levels and permissions come from `GET /api/v1/user/profile` (C3). Themes never decide access;
  they only ask.
- CMS layout areas are regions automatically. The cms API applies `required_access_level_ids` with
  the viewer's token.

## Translations (D13)

- In templates, use `{{ _("login.title") }}` or `{{ _("cart.items", count=n) }}` (`%(count)s`
  placeholders; there is no `str.format`).
- Lookup per language: operator → active chain → adapter catalogs.
- Fallback: resolved language → cms `default_language` → `en` → the key itself.
- The language is defined by the CMS: post language → `vbwd_lang` cookie → `Accept-Language`,
  capped to the cms `enabled_languages`.
- `<html lang>`, hreflang and the language switcher (`data-testid="language-switch-<lang>"`) come
  from `basic`. Keep them if you override `_shared/document.html.j2`.
- `basic` and the S152 adapters ship only `en.json`. A theme that wants German UI strings ships
  `translations/de.json`.

## Tokens and stylesheet order

`/_render/_theme/public/theme.css` is concatenated in this order:

1. `basic` (`static/_shared/*.css`, then `static/public/*.css`, sorted by file name);
2. the stylesheet directories adapters contribute, in registration order (the SPA's structural CSS);
3. each child theme, parent before child, so a child overrides both;
4. one `:root { … }` block with the merged `tokens.json`. The child's value wins, and each token is
   emitted once, sorted.

The page's **CMS Style** is linked **after** theme.css and keeps the final say on colour. Use the
fe-core token **names** (`--vbwd-color-primary`, …). The SPA never loads theme.css (R9); the two
renderers share tokens by name only. Keep literal colours out of structural CSS: colour belongs in
tokens and CMS Styles. A literal is allowed only as a token's fallback (see "Colour tokens" below).

The stylesheet URL is content-hashed (`?v=`) and served `immutable`, so a changed file means a new
URL.

## Colour tokens (S152-06d)

The adapters port the SPA's structural CSS. Where an SPA component already reads a token
(`var(--vbwd-color-primary, #3498db)`, `var(--color-text, #0f172a)`, …) the port keeps that
chain unchanged. Where the SPA hard-codes a literal colour (overlay dim, shadows, the post-hero
scrim, status tints, the palette presets), the port wraps the **exact SPA literal** as the
fallback of a named adapter token:

```css
.cms-menu-overlay--open { background: var(--vbwd-cms-menu-overlay, rgba(0,0,0,0.4)); }
.cms-menu__sub { box-shadow: 0 4px 12px var(--vbwd-cms-menu-dropdown-shadow, rgba(0,0,0,0.1)); }
```

So the default rendering is the SPA's, and every colour can be overridden.

**Rules** (enforced by each adapter's `test_ported_css` / `test_ported_component_css`):

- A literal colour may appear **only** as the fallback of a `var(--vbwd-…, <literal>)` token, or
  of one of the SPA's own `--color-*` chains, kept verbatim. Anywhere else (a bare literal, a
  literal next to a `var()`, the fallback of any other name) fails.
- Names follow `--vbwd-<adapter>-<component>-<role>`, kebab-case. They match the `tokens.json` key
  rule `^--vbwd-[a-z0-9-]+$`.
- One token has one default. Every token used in an adapter's CSS is listed below with that
  default, and every listed token is used.
- Each fallback equals the literal in the SPA component's `<style>`, and every SPA colour of a
  rendered rule is ported. Both are checked against the fe-user checkout when it is mounted.

**Override in a child theme**: add the token to `tokens.json`. It lands in theme.css's final
`:root` block:

```json
{"--vbwd-cms-menu-overlay": "rgba(15, 23, 42, 0.6)", "--vbwd-shop-order-status-pending-bg": "#fde68a"}
```

**Override in a CMS Style**: plain CSS. The style is linked after theme.css, so its `:root` wins:

```css
:root { --vbwd-cms-post-hero-scrim-start: rgba(0, 0, 0, 0.8); }
```

The palette-preset tokens (`--vbwd-cms-landing1-<preset>-*`,
`--vbwd-subscription-plan-collection-<preset>-*`) only apply while that preset class is on the
widget.

### theme (`--vbwd-base-*`, `--vbwd-login-*`)

From fe-user `vue/src/App.vue` (the global `*` / `body` rules and the `#app.app--public-light`
remap, ported onto `<body>` in the basic theme's `_shared/base.css`, because every themed page is
public) and `vue/src/views/Login.vue` (`public/login.css`, scoped to `.login-page`).

| Token | Where used | SPA default |
|---|---|---|
| `--vbwd-base-border-light` | `body` `--vbwd-border-light` | `#eeeeee` |
| `--vbwd-login-page-bg` | `.login-page` background-color | `#f5f5f5` |
| `--vbwd-login-card-bg` | `.login-card` background | `white` |
| `--vbwd-login-card-shadow` | `.login-card` box-shadow | `rgba(0, 0, 0, 0.1)` |
| `--vbwd-login-heading-text` | `.login-page h1` color | `#2c3e50` |
| `--vbwd-login-label-text` | `.login-page label` color | `#666` |
| `--vbwd-login-input-border` | `.login-page input` border | `#ddd` |
| `--vbwd-login-input-focus-border` | `.login-page input:focus` border-color | `#3498db` |
| `--vbwd-login-button-bg` | `.login-page button` background-color | `#3498db` |
| `--vbwd-login-button-text` | `.login-page button` color | `white` |
| `--vbwd-login-button-hover-bg` | `.login-page button:hover:not(:disabled)` background-color | `#2980b9` |
| `--vbwd-login-error-bg` | `.login-page .error` background-color | `#fee` |
| `--vbwd-login-error-text` | `.login-page .error` color | `#c00` |

### theme_cms (`--vbwd-cms-*`)

From fe-user `plugins/cms` CmsWidgetRenderer.vue (menu, slideshow), CmsPageTypeBase.vue (post hero), PostCard.vue, ContactForm.vue, CookieConsent.vue, AddonCatalog.vue and `plugins/landing1/Landing1View.vue` (NativePricingPlans: card shadows and the `landing1--<preset>` palettes).

| Token | Where used | SPA default |
|---|---|---|
| `--vbwd-cms-post-hero-scrim-start` | `.cms-post-hero__scrim` background | `rgba(0, 0, 0, 0.62)` |
| `--vbwd-cms-post-hero-scrim-middle` | `.cms-post-hero__scrim` background | `rgba(0, 0, 0, 0.18)` |
| `--vbwd-cms-post-hero-scrim-end` | `.cms-post-hero__scrim` background | `rgba(0, 0, 0, 0.05)` |
| `--vbwd-cms-post-hero-contrast-bg` | `.cms-post-hero__contrast` background | `rgba(0, 0, 0, 0.28)` |
| `--vbwd-cms-post-hero-tag-border` | `.cms-post-hero .cms-post-tag` border-color | `rgba(255, 255, 255, 0.4)` |
| `--vbwd-cms-post-hero-tag-bg` | `.cms-post-hero .cms-post-tag` background | `rgba(255, 255, 255, 0.14)` |
| `--vbwd-cms-post-hero-tag-hover-border` | `.cms-post-hero .cms-post-tag:hover` border-color | `rgba(255, 255, 255, 0.75)` |
| `--vbwd-cms-post-hero-tag-hover-bg` | `.cms-post-hero .cms-post-tag:hover` background | `rgba(255, 255, 255, 0.24)` |
| `--vbwd-cms-menu-overlay` | `.cms-menu-overlay--open` background | `rgba(0,0,0,0.4)` |
| `--vbwd-cms-menu-dropdown-shadow` | `.cms-menu__sub` box-shadow | `rgba(0,0,0,0.1)` |
| `--vbwd-cms-menu-drawer-shadow` | `.cms-menu` box-shadow | `rgba(0,0,0,0.15)` |
| `--vbwd-cms-slideshow-arrow-bg` | `.cms-slide__prev` background; `.cms-slide__next` background | `rgba(0,0,0,0.4)` |
| `--vbwd-cms-post-card-hover-shadow` | `.post-card--category:hover` box-shadow | `rgba(15, 23, 42, 0.18)` |
| `--vbwd-cms-contact-input-focus-ring` | `.contact-form-widget__input:focus` box-shadow | `rgba(52, 152, 219, 0.15)` |
| `--vbwd-cms-cookie-consent-shadow` | `.cookie-consent` box-shadow | `rgba(0, 0, 0, 0.25)` |
| `--vbwd-cms-cookie-settings-shadow` | `.cookie-consent__settings` box-shadow | `rgba(0, 0, 0, 0.15)` |
| `--vbwd-cms-addon-card-hover-shadow` | `.addon-card:hover` box-shadow | `rgba(0, 0, 0, 0.1)` |
| `--vbwd-cms-landing1-light-card-bg` | `.landing1--light` --l1-card-bg | `#ffffff` |
| `--vbwd-cms-landing1-light-text-heading` | `.landing1--light` --l1-text-heading | `#1f2937` |
| `--vbwd-cms-landing1-light-text-muted` | `.landing1--light` --l1-text-muted | `#6b7280` |
| `--vbwd-cms-landing1-light-border` | `.landing1--light` --l1-border | `#e5e7eb` |
| `--vbwd-cms-landing1-dark-primary` | `.landing1--dark` --l1-primary | `#3b82f6` |
| `--vbwd-cms-landing1-dark-primary-hover` | `.landing1--dark` --l1-primary-hover | `#2563eb` |
| `--vbwd-cms-landing1-dark-card-bg` | `.landing1--dark` --l1-card-bg | `#1f2937` |
| `--vbwd-cms-landing1-dark-text-heading` | `.landing1--dark` --l1-text-heading | `#f9fafb` |
| `--vbwd-cms-landing1-dark-text-muted` | `.landing1--dark` --l1-text-muted | `#9ca3af` |
| `--vbwd-cms-landing1-dark-border` | `.landing1--dark` --l1-border | `#374151` |
| `--vbwd-cms-landing1-dark-card-shadow` | `.landing1--dark` --l1-card-shadow | `rgba(0, 0, 0, 0.5)` |
| `--vbwd-cms-landing1-teal-primary` | `.landing1--teal` --l1-primary | `#14b8a6` |
| `--vbwd-cms-landing1-teal-primary-hover` | `.landing1--teal` --l1-primary-hover | `#0d9488` |
| `--vbwd-cms-landing1-teal-check` | `.landing1--teal` --l1-check | `#14b8a6` |
| `--vbwd-cms-landing1-indigo-primary` | `.landing1--indigo` --l1-primary | `#6366f1` |
| `--vbwd-cms-landing1-indigo-primary-hover` | `.landing1--indigo` --l1-primary-hover | `#4f46e5` |
| `--vbwd-cms-landing1-indigo-check` | `.landing1--indigo` --l1-check | `#6366f1` |
| `--vbwd-cms-landing1-emerald-primary` | `.landing1--emerald` --l1-primary | `#10b981` |
| `--vbwd-cms-landing1-emerald-primary-hover` | `.landing1--emerald` --l1-primary-hover | `#059669` |
| `--vbwd-cms-landing1-emerald-check` | `.landing1--emerald` --l1-check | `#10b981` |
| `--vbwd-cms-landing1-plan-card-hover-shadow` | `.landing1 .plan-card:hover` box-shadow | `rgba(0, 0, 0, 0.14)` |
| `--vbwd-cms-landing1-plan-card-featured-shadow` | `.landing1 .plan-card--featured` box-shadow | `rgba(0, 0, 0, 0.16)` |
| `--vbwd-cms-landing1-plan-badge-shadow` | `.landing1 .plan-card__badge` box-shadow | `rgba(0, 0, 0, 0.18)` |

### theme_shop (`--vbwd-shop-*`)

From fe-user `plugins/shop` ProductCatalog.vue, OrderHistory.vue + OrderDetail.vue (one status token pair shared by both views) and ShopCheckoutSummary.vue.

| Token | Where used | SPA default |
|---|---|---|
| `--vbwd-shop-sort-bg` | `.product-catalog__sort` background | `white` |
| `--vbwd-shop-product-card-hover-shadow` | `.product-card:hover` box-shadow | `rgba(0, 0, 0, 0.1)` |
| `--vbwd-shop-order-status-pending-bg` | `.order-row__status--pending` background; `.order-detail__status--pending` background | `#fff3cd` |
| `--vbwd-shop-order-status-pending-text` | `.order-row__status--pending` color; `.order-detail__status--pending` color | `#856404` |
| `--vbwd-shop-order-status-processing-bg` | `.order-row__status--processing` background; `.order-detail__status--processing` background | `#cce5ff` |
| `--vbwd-shop-order-status-processing-text` | `.order-row__status--processing` color; `.order-detail__status--processing` color | `#004085` |
| `--vbwd-shop-order-status-shipped-bg` | `.order-row__status--shipped` background; `.order-detail__status--shipped` background | `#d4edda` |
| `--vbwd-shop-order-status-shipped-text` | `.order-row__status--shipped` color; `.order-detail__status--shipped` color | `#155724` |
| `--vbwd-shop-order-status-delivered-bg` | `.order-row__status--delivered` background; `.order-detail__status--delivered` background | `#d4edda` |
| `--vbwd-shop-order-status-delivered-text` | `.order-row__status--delivered` color; `.order-detail__status--delivered` color | `#155724` |
| `--vbwd-shop-order-status-cancelled-bg` | `.order-row__status--cancelled` background; `.order-detail__status--cancelled` background | `#f8d7da` |
| `--vbwd-shop-order-status-cancelled-text` | `.order-row__status--cancelled` color; `.order-detail__status--cancelled` color | `#721c24` |
| `--vbwd-shop-summary-quantity-text` | `.cart-items-summary .plan-description` color | `#6b7280` |

### theme_subscription (`--vbwd-subscription-*`)

From fe-user `plugins/subscription` TariffPlanCollection.vue (shadows and the `tariff-plan-collection--<preset>` palettes), PlanCheckoutSummary.vue and the core CollectionToolbar.vue.

| Token | Where used | SPA default |
|---|---|---|
| `--vbwd-subscription-plan-collection-light-card-bg` | `.tariff-plan-collection--light` --tpc-card-bg | `#ffffff` |
| `--vbwd-subscription-plan-collection-light-text-heading` | `.tariff-plan-collection--light` --tpc-text-heading | `#1f2937` |
| `--vbwd-subscription-plan-collection-light-text-muted` | `.tariff-plan-collection--light` --tpc-text-muted | `#6b7280` |
| `--vbwd-subscription-plan-collection-light-border` | `.tariff-plan-collection--light` --tpc-border | `#e5e7eb` |
| `--vbwd-subscription-plan-collection-dark-primary` | `.tariff-plan-collection--dark` --tpc-primary | `#3b82f6` |
| `--vbwd-subscription-plan-collection-dark-primary-hover` | `.tariff-plan-collection--dark` --tpc-primary-hover | `#2563eb` |
| `--vbwd-subscription-plan-collection-dark-card-bg` | `.tariff-plan-collection--dark` --tpc-card-bg | `#1f2937` |
| `--vbwd-subscription-plan-collection-dark-text-heading` | `.tariff-plan-collection--dark` --tpc-text-heading | `#f9fafb` |
| `--vbwd-subscription-plan-collection-dark-text-muted` | `.tariff-plan-collection--dark` --tpc-text-muted | `#9ca3af` |
| `--vbwd-subscription-plan-collection-dark-border` | `.tariff-plan-collection--dark` --tpc-border | `#374151` |
| `--vbwd-subscription-plan-collection-dark-page-bg` | `.tariff-plan-collection--dark` --tpc-page-bg | `#111827` |
| `--vbwd-subscription-plan-collection-dark-card-shadow` | `.tariff-plan-collection--dark` --tpc-card-shadow | `rgba(0, 0, 0, 0.5)` |
| `--vbwd-subscription-plan-collection-teal-primary` | `.tariff-plan-collection--teal` --tpc-primary | `#14b8a6` |
| `--vbwd-subscription-plan-collection-teal-primary-hover` | `.tariff-plan-collection--teal` --tpc-primary-hover | `#0d9488` |
| `--vbwd-subscription-plan-collection-teal-check` | `.tariff-plan-collection--teal` --tpc-check | `#14b8a6` |
| `--vbwd-subscription-plan-collection-indigo-primary` | `.tariff-plan-collection--indigo` --tpc-primary | `#6366f1` |
| `--vbwd-subscription-plan-collection-indigo-primary-hover` | `.tariff-plan-collection--indigo` --tpc-primary-hover | `#4f46e5` |
| `--vbwd-subscription-plan-collection-indigo-check` | `.tariff-plan-collection--indigo` --tpc-check | `#6366f1` |
| `--vbwd-subscription-plan-collection-emerald-primary` | `.tariff-plan-collection--emerald` --tpc-primary | `#10b981` |
| `--vbwd-subscription-plan-collection-emerald-primary-hover` | `.tariff-plan-collection--emerald` --tpc-primary-hover | `#059669` |
| `--vbwd-subscription-plan-collection-emerald-check` | `.tariff-plan-collection--emerald` --tpc-check | `#10b981` |
| `--vbwd-subscription-plan-card-featured-shadow` | `.tariff-plan-card--featured` box-shadow | `rgba(0, 0, 0, 0.16)` |
| `--vbwd-subscription-plan-badge-shadow` | `.tariff-plan-card__badge` box-shadow | `rgba(0, 0, 0, 0.18)` |
| `--vbwd-subscription-toolbar-view-active-shadow` | `.collection-toolbar__view-btn.active` box-shadow | `rgba(0, 0, 0, 0.1)` |
| `--vbwd-subscription-summary-description-text` | `.plan-details .plan-description` color | `#6b7280` |

### theme_checkout (`--vbwd-checkout-*`)

From fe-user core `components/checkout` EmailBlock.vue, BillingAddressBlock.vue,
PaymentMethodsBlock.vue (`.email-block`, `.billing-address-block` and `.payment-methods-block`
share the `block-*` tokens) and TermsCheckbox.vue, plus `plugins/checkout` PublicCheckoutView.vue,
CheckoutConfirmationView.vue (one status token pair for the banner and the badge) and
TokenBundleCollection.vue, and `plugins/stripe-payment` StripeSuccessView.vue. fe-core
CouponInput.vue and PriceDisplay.vue keep their own `var()` chains. The unscoped `.card`, `.btn`,
`.public-checkout`, state and spinner rules are checkout-wide: the selling adapters' pay pages
(theme_booking) reuse them, so one `button-*` / `card-*` override restyles every checkout surface.

| Token | Where used | SPA default |
|---|---|---|
| `--vbwd-checkout-block-border` | `.email-block` border; `.billing-address-block` border; `.payment-methods-block` border | `#e0e0e0` |
| `--vbwd-checkout-block-bg` | `.email-block` background; `.billing-address-block` background; `.payment-methods-block` background | `white` |
| `--vbwd-checkout-email-success-border` | `.email-block.success` border-color | `#27ae60` |
| `--vbwd-checkout-email-success-bg` | `.email-block.success` background | `#e8f8f0` |
| `--vbwd-checkout-email-error-border` | `.email-block.error` border-color | `#e74c3c` |
| `--vbwd-checkout-block-heading-text` | `.email-block h3` color; `.billing-address-block h3` color; `.payment-methods-block h3` color | `#2c3e50` |
| `--vbwd-checkout-field-border` | `.email-block input` border; `.billing-address-block input` border; `.billing-address-block select` border | `#ddd` |
| `--vbwd-checkout-field-disabled-bg` | `.email-block input:disabled` background | `#f5f5f5` |
| `--vbwd-checkout-field-disabled-text` | `.email-block input:disabled` color | `#666` |
| `--vbwd-checkout-email-hint-text` | `.email-block .hint` color | `#666` |
| `--vbwd-checkout-email-hint-error-text` | `.email-block .text-red` color | `#e74c3c` |
| `--vbwd-checkout-button-primary-bg` | `.email-block .btn.primary` background; `.terms-checkbox .btn.primary` background; `.btn.primary` background-color; `.stripe-success .btn-primary` background | `#3498db` |
| `--vbwd-checkout-button-primary-text` | `.email-block .btn.primary` color; `.terms-checkbox .btn.primary` color; `.btn.primary` color; `.stripe-success .btn-primary` color | `white` |
| `--vbwd-checkout-button-primary-hover-bg` | `.email-block .btn.primary:hover:not(:disabled)` background; `.terms-checkbox .btn.primary:hover` background; `.btn.primary:hover:not(:disabled)` background-color; `.stripe-success .btn-primary:hover` background | `#2980b9` |
| `--vbwd-checkout-button-primary-disabled-bg` | `.email-block .btn.primary:disabled` background; `.btn.primary:disabled` background-color | `#95a5a6` |
| `--vbwd-checkout-button-secondary-bg` | `.email-block .btn.secondary` background; `.btn.secondary` background-color | `#ecf0f1` |
| `--vbwd-checkout-email-button-secondary-text` | `.email-block .btn.secondary` color | `#333` |
| `--vbwd-checkout-button-secondary-hover-bg` | `.email-block .btn.secondary:hover` background; `.btn.secondary:hover` background-color | `#bdc3c7` |
| `--vbwd-checkout-email-error-text` | `.email-block .error-message` color | `#e74c3c` |
| `--vbwd-checkout-strength-weak` | `.email-block .strength-bar.weak` background; `.email-block .strength-label.weak` color | `#e74c3c` |
| `--vbwd-checkout-strength-track` | `.email-block .strength-bar.weak` background; `.email-block .strength-bar.medium` background | `#ddd` |
| `--vbwd-checkout-strength-medium` | `.email-block .strength-bar.medium` background; `.email-block .strength-label.medium` color | `#f39c12` |
| `--vbwd-checkout-strength-strong` | `.email-block .strength-bar.strong` background; `.email-block .strength-label.strong` color | `#27ae60` |
| `--vbwd-checkout-link-text` | `.email-block .forgot-password-link` color; `.terms-checkbox .checkbox-label a` color | `#3498db` |
| `--vbwd-checkout-email-logged-in-text` | `.email-block .logged-in-info` color | `#27ae60` |
| `--vbwd-checkout-field-label-text` | `.billing-address-block label` color | `#333` |
| `--vbwd-checkout-field-focus-border` | `.billing-address-block input:focus` border-color; `.billing-address-block select:focus` border-color | `#3498db` |
| `--vbwd-checkout-field-focus-ring` | `.billing-address-block input:focus` box-shadow; `.billing-address-block select:focus` box-shadow | `rgba(52, 152, 219, 0.1)` |
| `--vbwd-checkout-field-error-border` | `.billing-address-block input.error` border-color; `.billing-address-block select.error` border-color | `#e74c3c` |
| `--vbwd-checkout-method-border` | `.payment-methods-block .method-option` border | `#e0e0e0` |
| `--vbwd-checkout-method-hover-border` | `.payment-methods-block .method-option:hover` border-color | `#3498db` |
| `--vbwd-checkout-method-selected-border` | `.payment-methods-block .method-option.selected` border-color | `#3498db` |
| `--vbwd-checkout-method-selected-bg` | `.payment-methods-block .method-option.selected` background | `#f0f7ff` |
| `--vbwd-checkout-method-name-text` | `.payment-methods-block .method-name` color | `#2c3e50` |
| `--vbwd-checkout-method-description-text` | `.payment-methods-block .method-description` color | `#666` |
| `--vbwd-checkout-method-instructions-bg` | `.payment-methods-block .method-instructions` background | `#f8f9fa` |
| `--vbwd-checkout-method-instructions-text` | `.payment-methods-block .method-instructions` color | `#495057` |
| `--vbwd-checkout-method-state-text` | `.payment-methods-block .error` color; `.payment-methods-block .empty` color | `#666` |
| `--vbwd-checkout-method-error-text` | `.payment-methods-block .error` color | `#e74c3c` |
| `--vbwd-checkout-link-hover-text` | `.terms-checkbox .checkbox-label a:hover` color | `#2980b9` |
| `--vbwd-checkout-popup-overlay` | `.terms-checkbox .popup-overlay` background | `rgba(0, 0, 0, 0.5)` |
| `--vbwd-checkout-popup-bg` | `.terms-checkbox .popup-content` background | `white` |
| `--vbwd-checkout-popup-shadow` | `.terms-checkbox .popup-content` box-shadow | `rgba(0, 0, 0, 0.15)` |
| `--vbwd-checkout-popup-divider` | `.terms-checkbox .popup-header` border-bottom; `.terms-checkbox .popup-footer` border-top | `#eee` |
| `--vbwd-checkout-popup-heading-text` | `.terms-checkbox .popup-header h3` color; `.terms-checkbox .popup-body h3` color; `.terms-checkbox .popup-body h4` color | `#2c3e50` |
| `--vbwd-checkout-popup-close-text` | `.terms-checkbox .close-btn` color | `#666` |
| `--vbwd-checkout-popup-close-hover-text` | `.terms-checkbox .close-btn:hover` color | `#333` |
| `--vbwd-checkout-popup-body-text` | `.terms-checkbox .popup-body` color | `#333` |
| `--vbwd-checkout-title-text` | `.public-checkout h1` color | `#2c3e50` |
| `--vbwd-checkout-order-total-border` | `.order-total` border-top | `#e5e7eb` |
| `--vbwd-checkout-state-text` | `.loading-state` color; `.error-state` color; `.no-plan` color | `#666` |
| `--vbwd-checkout-spinner-track` | `.spinner` border | `#f3f3f3` |
| `--vbwd-checkout-spinner-indicator` | `.spinner` border-top | `#3498db` |
| `--vbwd-checkout-card-bg` | `.card` background | `white` |
| `--vbwd-checkout-card-shadow` | `.card` box-shadow | `rgba(0, 0, 0, 0.05)` |
| `--vbwd-checkout-card-heading-text` | `.card h2` color | `#2c3e50` |
| `--vbwd-checkout-card-heading-border` | `.card h2` border-bottom | `#eee` |
| `--vbwd-checkout-requirements-bg` | `.requirements` background | `#fff3cd` |
| `--vbwd-checkout-requirements-border` | `.requirements` border | `#ffc107` |
| `--vbwd-checkout-requirements-text` | `.requirements p` color; `.requirements ul` color | `#856404` |
| `--vbwd-checkout-button-secondary-text` | `.btn.secondary` color | `#2c3e50` |
| `--vbwd-checkout-error-message-bg` | `.error-message` background | `#fee` |
| `--vbwd-checkout-error-message-text` | `.error-message` color | `#c00` |
| `--vbwd-checkout-status-paid-bg` | `.checkout-confirmation .confirmation-banner--paid` background; `.checkout-confirmation .confirmation-banner--authorized` background; `.checkout-confirmation .status-badge.paid` background; `.checkout-confirmation .status-badge.authorized` background | `#dcfce7` |
| `--vbwd-checkout-status-paid-text` | `.checkout-confirmation .confirmation-banner--paid` color; `.checkout-confirmation .confirmation-banner--authorized` color; `.checkout-confirmation .status-badge.paid` color; `.checkout-confirmation .status-badge.authorized` color | `#166534` |
| `--vbwd-checkout-status-pending-bg` | `.checkout-confirmation .confirmation-banner--pending` background; `.checkout-confirmation .status-badge.pending` background | `#fef9c3` |
| `--vbwd-checkout-status-pending-text` | `.checkout-confirmation .confirmation-banner--pending` color; `.checkout-confirmation .status-badge.pending` color | `#854d0e` |
| `--vbwd-checkout-status-failed-bg` | `.checkout-confirmation .confirmation-banner--failed` background; `.checkout-confirmation .confirmation-banner--cancelled` background; `.checkout-confirmation .status-badge.failed` background; `.checkout-confirmation .status-badge.cancelled` background | `#fee2e2` |
| `--vbwd-checkout-status-failed-text` | `.checkout-confirmation .confirmation-banner--failed` color; `.checkout-confirmation .confirmation-banner--cancelled` color; `.checkout-confirmation .status-badge.failed` color; `.checkout-confirmation .status-badge.cancelled` color | `#991b1b` |
| `--vbwd-checkout-confirmation-row-border` | `.checkout-confirmation .confirmation-row` border-bottom | `#f3f4f6` |
| `--vbwd-checkout-confirmation-label-text` | `.checkout-confirmation .confirmation-label` color | `#6b7280` |
| `--vbwd-checkout-confirmation-value-text` | `.checkout-confirmation .confirmation-value` color | `#1f2937` |
| `--vbwd-checkout-confirmation-mono-text` | `.checkout-confirmation .confirmation-mono` color | `#6b7280` |
| `--vbwd-checkout-line-items-heading-text` | `.checkout-confirmation .line-items h3` color | `#374151` |
| `--vbwd-checkout-line-items-header-text` | `.checkout-confirmation .line-items-table th` color | `#6b7280` |
| `--vbwd-checkout-line-items-header-border` | `.checkout-confirmation .line-items-table th` border-bottom | `#e5e7eb` |
| `--vbwd-checkout-line-items-row-border` | `.checkout-confirmation .line-items-table td` border-bottom | `#f3f4f6` |
| `--vbwd-checkout-line-items-footer-border` | `.checkout-confirmation .line-items-table tfoot td` border-top | `#e5e7eb` |
| `--vbwd-checkout-line-items-total-text` | `.checkout-confirmation .total-label` color | `#374151` |
| `--vbwd-checkout-token-bundle-add-text` | `.token-bundle-card__add` color | `#fff` |

### theme_booking (`--vbwd-booking-*`)

From fe-user `plugins/booking` BookingCatalogue.vue, BookingResourceDetail.vue, BookingForm.vue, BookingCheckout.vue, BookingSuccess.vue (one status token pair for the banner and the badge) and BookingCancel.vue. The pay page's shared `.card`, `.btn` and `.requirements` colours are theme_checkout's `--vbwd-checkout-*` tokens (S152-07c).

| Token | Where used | SPA default |
|---|---|---|
| `--vbwd-booking-card-hover-shadow` | `.ghrm-pkg-card:hover` box-shadow | `rgba(52,152,219,.1)` |
| `--vbwd-booking-gallery-thumb-hover-border` | `.booking-gallery__thumb:hover` border-color | `#93c5fd` |
| `--vbwd-booking-detail-description-text` | `.ghrm-detail-description` color | `#4b5563` |
| `--vbwd-booking-badge-version-bg` | `.ghrm-badge--version` background | `#e8f4fd` |
| `--vbwd-booking-badge-version-text` | `.ghrm-badge--version` color | `#1a73e8` |
| `--vbwd-booking-cta-hover-bg` | `.ghrm-cta-btn:hover:not(:disabled)` background | `#2980b9` |
| `--vbwd-booking-error-text` | `.ghrm-error` color | `#dc2626` |
| `--vbwd-booking-date-picker-label-text` | `.booking-date-picker label` color | `#374151` |
| `--vbwd-booking-slot-selected-bg` | `.booking-slot.selected` background | `#e8f4fd` |
| `--vbwd-booking-form-label-text` | `.booking-form__field label` color | `#374151` |
| `--vbwd-booking-form-required-text` | `.booking-form__required` color | `#dc2626` |
| `--vbwd-booking-status-paid-bg` | `.confirmation-banner--paid` background; `.confirmation-banner--authorized` background; `.status-badge.paid` background; `.status-badge.authorized` background | `#dcfce7` |
| `--vbwd-booking-status-paid-text` | `.confirmation-banner--paid` color; `.confirmation-banner--authorized` color; `.status-badge.paid` color; `.status-badge.authorized` color | `#166534` |
| `--vbwd-booking-status-pending-bg` | `.confirmation-banner--pending` background; `.status-badge.pending` background | `#fef9c3` |
| `--vbwd-booking-status-pending-text` | `.confirmation-banner--pending` color; `.status-badge.pending` color | `#854d0e` |
| `--vbwd-booking-resource-description-text` | `.resource-desc` color | `#4b5563` |
| `--vbwd-booking-cancel-banner-bg` | `.cancel-banner` background | `#fef9c3` |
| `--vbwd-booking-cancel-banner-text` | `.cancel-banner` color | `#854d0e` |

## Twig → Jinja cheat sheet

| Twig | Jinja (theme) |
|---|---|
| `{% extends "base.html.twig" %}` | `{% extends "_shared/document.html.j2" %}` |
| `{% extends "@Parent/x.html.twig" %}` | `{% extends "@basic/x.html.j2" %}` |
| `{{ parent() }}` | `{{ super() }}` |
| `{% block content %}…{% endblock %}` | same |
| `{% include "x.twig" with {a: 1} %}` | `{% with a = 1 %}{% include "x.html.j2" %}{% endwith %}` |
| `{% import "forms.twig" as forms %}` | `{% import "_shared/macros/forms.html.j2" as forms %}` |
| `{{ var\|raw }}` | `{{ var\|safe }}` (only for trusted HTML: autoescape is on) |
| `{{ 'key'\|trans }}` | `{{ _('key') }}` |
| `{% for x in xs %}…{% else %}…{% endfor %}` | same |
| `{{ x ?? 'd' }}` | `{{ x\|default('d') }}` |
| `{% if x is defined %}` | same |
| `~` (concat) | `~` |
| `{{ asset('a.css') }}` | `{{ asset('_shared/a.css') }}` (hashed theme static URL) |

The environment is a `SandboxedEnvironment` with autoescape on (dunder access is blocked) and
`StrictUndefined` under test. Template suffix: `.html.j2`.

## Testing

- **Unit (your plugin repo):** register your descriptor on top of `BASIC_THEME_DESCRIPTOR` in a
  fresh `ThemeRegistry`. Assert:
  - the chain;
  - that your overrides win, through `ThemeTemplateLoader(...).get_source`;
  - that your tokens land in `StylesheetBuilder().build(...)`.

  See `plugins/theme/tests/unit/test_theme_demo_fixture.py` for a template.
- **Adapter DOM contracts with your theme active:** run the adapters' suites, e.g.
  `bin/pre-commit-check.sh --plugin theme_cms --full`, with `active_theme` pointing at your slug.
- **E2E fixture `theme_demo`:** `plugins/theme/tests/fixtures/theme_demo/` is a minimal child of
  `basic`. It overrides `cms/page_types/page.html.j2` (adds `data-testid="theme-demo-banner"`)
  and the `--vbwd-color-primary` token. It is **not** in `plugins.json.dist`. To run
  `vue/tests/e2e/frontend-mode/child-theme-override.spec.ts`:

  ```bash
  cp -r vbwd-backend/plugins/theme/tests/fixtures/theme_demo vbwd-backend/plugins/theme_demo
  # enable it (admin UI, or POST /api/v1/admin/plugins/theme_demo/enable), then:
  (cd vbwd-backend && docker compose restart api)
  E2E_FRONTEND_MODE=theme E2E_BASE_URL=http://localhost:8080 \
    npx playwright test vue/tests/e2e/frontend-mode/child-theme-override.spec.ts   # in vbwd-fe-user
  rm -rf vbwd-backend/plugins/theme_demo   # afterwards (disable it first)
  ```

  The spec sets `active_theme: demo` itself and restores the saved theme config afterwards. It
  skips when `theme_demo` is not enabled.
