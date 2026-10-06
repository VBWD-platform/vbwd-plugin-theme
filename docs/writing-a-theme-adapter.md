# Writing a theme adapter (the themed twin of an fe-user plugin)

When a new fe-user plugin gets a **public** route or a CMS widget, it also needs a themed twin. That
twin is a backend plugin `theme_<x>` that renders the same pages and widgets server-side when
`VBWD_FRONTEND_MODE=theme`. Modes, routing and core seams are covered in
`docs/architecture/frontend-modes.md`. Restyling (child themes) is covered in `writing-a-theme.md`.

> **Engineering requirements (BINDING):** TDD-first · DevOps-first · SOLID · DI · DRY ·
> Liskov · clean code · **NO OVERENGINEERING**.

## Why you must write one: the coverage oracle (D11)

- `vbwd-fe-user/vue/tests/unit/theme-route-coverage.spec.ts` dumps every public fe-user route into
  `vue/tests/e2e/theme-route-coverage.json` and fails when that file is stale. Adding a route
  forces a regenerate:

  ```bash
  UPDATE_THEME_COVERAGE=1 npx vitest run vue/tests/unit/theme-route-coverage.spec.ts
  ```

- In the theme e2e leg, `vue/tests/e2e/frontend-mode/theme-coverage.spec.ts` visits each sample URL
  of every enabled plugin and requires `<meta name="vbwd-frontend" content="theme">`.
- So a new public route turns the theme leg **red** until your adapter themes it. Until it is
  built, list the route in `vue/tests/e2e/theme-coverage-pending.json`.
- The spec also fails when a pending route **is** already themed. Remove the entry in the same
  change that themes it.
- `/dashboard*` and `/tuktuk*` are never in the file: they are SPA-only (D7).

## Rules

1. **Presentation only (D3).** Every read and write goes through `call_api(theme_request, method,
   "/api/v1/…")`. That is an in-process dispatch (core C2) to the **same** endpoint the Vue plugin
   calls, with the caller's allow-listed headers forwarded, so RBAC, GDPR scoping, pricing and
   rate limits stay in one place.
   - Never import the domain plugin. The oracle `test_domain_plugins_are_frontend_agnostic.py`
     walks your code and tests.
   - Seed test data through the domain's admin HTTP API.
   - You may read the domain plugin's **config** through `current_app.config_store` (read-only).
2. **The domain plugin knows nothing about you (R1).** It never imports `plugins.theme*`, never
   depends on a theme plugin and never reads `VBWD_FRONTEND_MODE`.
3. **Same browser contract as the SPA (D2):**
   - the same URLs, `data-testid`s, copy and localStorage keys;
   - copy the DOM contract from the Vue templates and the e2e specs, with line references, into a
     DOM-contract test;
   - seed your `translations/en.json` from the fe-user plugin's `locales/en.json`.
4. **Same toggle.** Each page, fragment and descriptor names its `owner_fe_user_plugin`. It answers
   only while that fe-user plugin is enabled in `fe-user-plugins.json`; otherwise it 404s and nginx
   falls back to the SPA.
5. **Anonymous navigations (D4).** Pages render anonymously. Anything identity-dependent goes in
   an `{% access %}` / `{% permission %}` / `{% region %}` tag and is re-rendered for the viewer
   through `/regions`. Auth-only pages use `auth=USER_PAGE`, which renders with
   `data-auth="pending"`.
6. **Register in `on_enable`, once.**
   - The registries are sealed when the theme mounts its blueprint at boot, so a late registration
     raises.
   - Enabling an adapter at runtime therefore needs an api restart.
   - Guard against double registration, as the existing adapters do: check whether your templates
     path is already contributed.

## Skeleton

```
plugins/theme_x/
├── __init__.py          # ThemeXPlugin; dependencies=["theme>=1.0", "x", …]
├── config.json · admin-config.json · populate_db.py (no-op) · pyproject.toml
├── theme_x/
│   ├── registration.py  # x_pages(), x_fragments(), x_components()
│   ├── templates/x/…    # contributed templates (rank below every theme)
│   ├── translations/en.json
│   └── stylesheets/{_shared,public}/*.css   # the SPA's structural CSS; literal colours only as
│                                            # --vbwd-<adapter>-* token fallbacks (writing-a-theme.md)
└── tests/{unit,integration}/
```

```python
def on_enable(self) -> None:
    theme_plugin = resolve_theme_plugin()
    theme_registry = theme_plugin.theme_registry
    if TEMPLATES_DIRECTORY in theme_registry.contributed_template_paths():
        return
    theme_registry.add_contributed_template_path(TEMPLATES_DIRECTORY)
    theme_registry.add_contributed_translation_path(TRANSLATIONS_DIRECTORY)
    theme_registry.add_contributed_stylesheet_path(STYLESHEETS_DIRECTORY)
    for page in x_pages():
        theme_plugin.page_registry.register(page)
    for fragment in x_fragments():
        theme_plugin.fragment_registry.register(fragment)
```

The `theme` platform and the sibling adapters are declared dependencies, so you may import their
public modules (`plugins.theme.theme.*`, `plugins.theme_cms.theme_cms.*`, …). Adapter-to-adapter
imports are allowed; adapter-to-domain imports are not.

## Extension points

### Pages: `ThemePage` (`plugins/theme/theme/page_registry.py`)

```python
ThemePage(
    rule="/x/<slug>",                 # the PUBLIC path (W2); never /dashboard*, /tuktuk*, /_render*
    endpoint="x_detail",
    owner_fe_user_plugin="x",         # the fe-user manifest key
    priority=0,                       # the cms catch-all is -1000
    auth=PUBLIC_PAGE,                 # or USER_PAGE → data-auth="pending"
    template="x/detail.html.j2",
    build_context=build_detail_context,   # (ThemeRequest) -> dict; fetch via call_api
)
```

- The theme renders the template, so your page never builds a response.
- A `ThemeApiError` from `call_api` maps to the themed 404/403/500. A themed 404 becomes the SPA
  under nginx's `error_page`.
- Pages answer only to nginx's `X-VBWD-Render: 1`.
- Return `page_language` in the context to pin the language (CMS posts do).
- Return `language_alternates` + `current_url` to fill hreflang and the switcher.
- Pages fe-user renders **inside a CMS page** (`/booking` → CMS slug `booking`) reuse theme_cms's
  pipeline: `CmsPages(...)` / `cms_slug_page_context(request, cms_slug)`, with the template
  `cms/dispatch.html.j2`.

### Fragments: `ThemeFragment` (`plugins/theme/theme/fragment_registry.py`)

- htmx islands live at `/_render/_fragment/<name>`, GET by default and `methods=("GET","POST")` for
  forms.
- Inputs arrive in `theme_request.query_args`.
- Raise `ThemeFragmentRedirect(location)` to end the flow with a navigation (`HX-Redirect`), e.g.
  to a provider's hosted page or the confirmation page.
- Responses are `no-store` and absent in vue mode.

### CMS widgets: `ComponentTemplate` (`plugins/theme_cms/theme_cms/registries.py`)

- `ComponentTemplate(name="XCatalogue", template="cms/components/x_catalogue.html.j2",
  build_context=...)`. The `name` is the one the Vue plugin passes to `registerCmsVueComponent`.
- The context builder receives `(widget_config, page, route_params, theme_request)`.
- Register it on `plugin_manager.get_plugin("theme_cms").component_registry`.
- A widget with no themed twin renders a `.cms-widget--vue-missing` comment, so add one for every
  name the fe-user plugin registers. theme_cms's tests compare its list against fe-user `index.ts`.
- New CMS page types: `page_type_registry.register("<type>", "<template>")`.

### Checkout sources: `CheckoutSource` (`plugins/theme_checkout/theme_checkout/checkout_sources.py`)

- A purchasable domain plugs into the themed `/checkout`:
  `CheckoutSource(id="x", matches=..., load_summary=..., submit=..., summary_template=...,
  priority=0, cart_key=CORE_CART_KEY | "vbwd_x_cart" | None)`.
- `submit` calls the domain's own checkout endpoint through `call_api`. The shared form supplies
  the email, billing, payment method, terms and coupon blocks, and `dispatch_after_submit` routes
  to the confirmation page or the payment page.
- Register on `plugin_manager.get_plugin("theme_checkout").source_registry` and depend on
  `theme_checkout`.

### Payment providers: `PaymentFlowDescriptor` (`plugins/theme_checkout/theme_checkout/payment/flow_descriptors.py`)

- Payment pages only exist after a checkout, so they live in `theme_checkout` (sub-package
  `payment/`); there is no separate payment adapter. Its templates are under
  `templates/payment/` and its messages share theme_checkout's `translations/<lang>.json`.

- One descriptor per provider: `provider`, `fe_user_plugin`, `payment_method_code`, `kind`,
  `api_prefix`, `success_handling`, `create_path`, `session_url_field`.
- The `redirect` kind is built: an htmx POST creates the session and answers `HX-Redirect`.
- Registering a `poll` or `custom` descriptor raises `PaymentFlowRegistrationError` until S153
  builds those kinds.
- A provider is a descriptor plus at most one template. You don't touch the platform or the payment
  plugin.

## Testing

- **Unit:**
  - page, fragment and component registration;
  - context builders with a faked `call_api` (fake the C2 client, the DI port);
  - the DOM contract against the Vue markup;
  - the translation drift test.
- **Integration (real `create_app`, theme mode):**
  - routes exist only in theme mode, and only while the owner is enabled;
  - a full flow seeded through the admin HTTP API;
  - GDPR: user A never sees B's data;
  - the provider SDK stubbed at its HTTP boundary only.
- **Gate:** `bin/pre-commit-check.sh --plugin theme_x --full`. The Black step sees nothing in
  gitignored plugin dirs, so also run `black --check` on your files explicitly. Then keep
  `--plugin theme --full` and the core oracles green.
- **E2E:**
  - drop the routes from `theme-coverage-pending.json` (if they were there);
  - run the parity suite and `vue/tests/e2e/frontend-mode/` with `E2E_FRONTEND_MODE=theme` against
    a theme-mode stack;
  - the specs must also stay green in vue mode.
