"""S152 16d — the e2e spec drift guard tolerates shifted lines, never a lost selector."""
from plugins.theme.tests.e2e_spec_contract import spec_selector_drift

SPEC = "tests/e2e/flow.spec.ts"
OTHER_SPEC = "tests/e2e/other.spec.ts"


def _write_spec(root, relative_path, text):
    spec_path = root / relative_path
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(text, encoding="utf-8")


def test_a_selector_that_moved_to_another_line_is_not_drift(tmp_path):
    _write_spec(tmp_path, SPEC, "// a new comment\n\npage.locator('.pay-button');\n")

    assert spec_selector_drift(tmp_path, [(".pay-button", SPEC, 1)]) == []


def test_a_renamed_selector_is_drift_naming_its_documented_line(tmp_path):
    _write_spec(tmp_path, SPEC, "page.locator('.pay-now-button');\n")

    drift = spec_selector_drift(tmp_path, [(".pay-button", SPEC, 7)])

    assert drift == [f"{SPEC} carries .pay-button 0 time(s), pinned 1 (lines 7)"]


def test_every_pin_needs_its_own_use_in_the_spec(tmp_path):
    _write_spec(tmp_path, SPEC, "page.click('.ghrm-cta-btn');\n")
    pins = [(".ghrm-cta-btn", SPEC, 3), (".ghrm-cta-btn", SPEC, 9)]

    assert spec_selector_drift(tmp_path, pins) == [
        f"{SPEC} carries .ghrm-cta-btn 1 time(s), pinned 2 (lines 3, 9)"
    ]


def test_uses_are_counted_per_spec(tmp_path):
    _write_spec(tmp_path, SPEC, "page.locator('textarea');\n")
    _write_spec(tmp_path, OTHER_SPEC, "page.locator('input');\n")
    pins = [("textarea", SPEC, 1), ("textarea", OTHER_SPEC, 1)]

    assert spec_selector_drift(tmp_path, pins) == [
        f"{OTHER_SPEC} carries textarea 0 time(s), pinned 1 (lines 1)"
    ]
