"""S152 16d — the drift guard of the adapters' e2e DOM contracts.

Shared by the theme plugin and its adapters' tests. A contract pins each
fe-user Playwright selector it proves in the themed output as ``(selector text,
spec path under fe-user, line)``. The line documents where the spec uses it:
editing a spec shifts lines, so the guard does not read it. What it guards is
the selector itself — the spec must still carry the verbatim text at least once
per pin, so a renamed or dropped use (even one of two) turns the contract red.
"""
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Tuple

# (selector text verbatim in the spec, spec path under fe-user, documented line)
SpecPin = Tuple[str, str, int]


def spec_selector_drift(fe_user_root: Path, pins: Iterable[SpecPin]) -> List[str]:
    """Pinned selectors a spec no longer uses as often as the contract pins them."""
    pin_list = list(pins)
    pins_per_use = Counter((spec, selector) for selector, spec, _line in pin_list)
    drifted = []
    for (spec, selector), pinned in pins_per_use.items():
        found = (fe_user_root / spec).read_text(encoding="utf-8").count(selector)
        if found < pinned:
            lines = ", ".join(
                str(line)
                for pin_selector, pin_spec, line in pin_list
                if (pin_spec, pin_selector) == (spec, selector)
            )
            drifted.append(
                f"{spec} carries {selector} {found} time(s), pinned {pinned} "
                f"(lines {lines})"
            )
    return drifted
