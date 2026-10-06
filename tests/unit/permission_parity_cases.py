"""Permission wildcard parity table, copied from fe-user ``hasUserPermission``.

Source of truth: ``vbwd-fe-user/vue/src/api/index.ts`` (``hasUserPermission``,
~line 138)::

    if (perms.includes('*')) return true;
    if (perms.includes(permission)) return true;
    return perms.some((p) => p.endsWith('.*') && permission.startsWith(p.slice(0, -1)));

Drift note: if that function changes, update this table and the theme's
``viewer_has_permission`` together — the two renderers must agree.

Each case: (granted permissions, requested permission, expected).
"""
PERMISSION_PARITY_CASES = (
    (("*",), "booking.manage", True),
    (("*",), "anything.at.all", True),
    (("booking.manage",), "booking.manage", True),
    (("booking.view",), "booking.manage", False),
    (("booking.*",), "booking.manage", True),
    (("booking.*",), "booking.resources.edit", True),
    (("booking.*",), "booking", False),
    (("booking.*",), "bookingx.manage", False),
    (("shop.orders.*",), "shop.orders.view", True),
    (("shop.orders.*",), "shop.view", False),
    ((".*",), "booking.manage", False),
    (("booking",), "booking.manage", False),
    ((), "booking.manage", False),
    (("shop.view", "booking.*"), "booking.manage", True),
)
