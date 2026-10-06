# vbwd-plugin-theme

`theme` is the theme platform: the Jinja2 engine, the `basic` theme, the template/theme registries and the `/_render` router that the `theme_*` adapters plug into. It renders only when the backend runs with
`VBWD_FRONTEND_MODE=theme`; in the default `vue` mode it mounts no page routes and the
Vue SPA keeps serving everything. Dependencies: none.
Design and roadmap: sprint S152 (`docs/dev_log/20260930/sprints/S152_twig_theme_platform_server_rendered_surfaces.md` in the vbwd-sdk workspace).

## Pre-commit

`bin/pre-commit-check.sh` is this repo's gate (the same file in all seven theme repos; the plugin
name comes from the repo directory, `theme` or `vbwd-plugin-theme`):

```bash
bin/pre-commit-check.sh             # = --full: lint + unit + integration
bin/pre-commit-check.sh --quick     # lint + unit
bin/pre-commit-check.sh --lint      # / --unit / --integration: one part only
bin/pre-commit-check.sh --e2e       # the walkthrough tests/e2e/walkthrough-theme.spec.ts (@theme)
bin/pre-commit-check.sh --help
```

- Inside an SDK checkout (`vbwd-backend/plugins/theme`) lint, unit and integration run through
  `vbwd-backend/bin/pre-commit-check.sh --plugin theme` (docker test services, shared test DB),
  plus Black and Flake8 over this repo's files (the backend gate's Black cannot see gitignored
  plugin dirs) and `node --test` on each `tests/js/*.test.mjs`.
- A standalone clone needs `VBWD_BACKEND_DIR=/path/to/vbwd-backend` (with the plugins this one
  depends on in its `plugins/`); the gate symlinks this repo in as `plugins/theme` and mounts it
  into the test containers. Without it, the gate prints the setup steps and exits 2.
- `--e2e` needs a `vbwd-fe-user` checkout (`VBWD_FE_USER_DIR`, default the SDK sibling) and a stack
  in theme mode at `E2E_BASE_URL` (default `http://localhost:8080`); it warns when
  `/_render/_theme/mode` does not answer 200. See `docs/architecture/frontend-modes.md` in the
  vbwd-sdk workspace.
- Exit codes: 0 ok · 1 static analysis · 2 unit tests or setup · 3 integration · 4 e2e.
