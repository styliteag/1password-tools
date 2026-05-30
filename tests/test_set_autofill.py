"""Offline unit tests for the pure logic of set_autofill.py.

These tests do not touch 1Password, the SDK, or the network. They cover the
decision logic that determines which items are edited, skipped, or stripped.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onepassword import AutofillBehavior, ItemCategory, ItemFieldType, ItemState

import set_autofill as sa


def field(field_id="", label="", field_type=ItemFieldType.TEXT):
    return SimpleNamespace(id=field_id, label=label, field_type=field_type)


def website(behavior):
    return SimpleNamespace(url="https://e.example", label="", autofill_behavior=behavior)


def overview(category=ItemCategory.LOGIN, behaviors=(AutofillBehavior.ANYWHEREONWEBSITE,),
             state=ItemState.ACTIVE):
    return SimpleNamespace(
        category=category,
        state=state,
        websites=[website(b) for b in behaviors],
    )


# --- overview_needs_change -------------------------------------------------

def test_needs_change_when_behavior_differs():
    assert sa.overview_needs_change(overview(behaviors=(AutofillBehavior.ANYWHEREONWEBSITE,)))


def test_no_change_when_already_target():
    assert not sa.overview_needs_change(overview(behaviors=(AutofillBehavior.EXACTDOMAIN,)))


def test_no_change_for_non_login_category():
    assert not sa.overview_needs_change(overview(category=ItemCategory.SECURENOTE))


def test_no_change_for_archived_item():
    assert not sa.overview_needs_change(overview(state=ItemState.ARCHIVED))


def test_mixed_websites_need_change():
    ov = overview(behaviors=(AutofillBehavior.EXACTDOMAIN, AutofillBehavior.ANYWHEREONWEBSITE))
    assert sa.overview_needs_change(ov)


# --- risky_reason ----------------------------------------------------------

def test_risky_unsupported_field():
    item = SimpleNamespace(
        fields=[field(field_type=ItemFieldType.UNSUPPORTED)], files=[], document=None)
    assert sa.risky_reason(item) is not None


def test_risky_file_attachment():
    item = SimpleNamespace(fields=[], files=["x"], document=None)
    assert sa.risky_reason(item) == "file attachment"


def test_not_risky_plain_login():
    item = SimpleNamespace(
        fields=[field("username", "username"), field("password", "password",
                ItemFieldType.CONCEALED)], files=[], document=None)
    assert sa.risky_reason(item) is None


# --- is_unsupported_field_error --------------------------------------------

@pytest.mark.parametrize("msg", [
    "cannot update item: Editing is not supported for unsupported fields",
    "invalid user input: encountered unsupported field",
])
def test_unsupported_error_detected(msg):
    assert sa.is_unsupported_field_error(Exception(msg))


def test_other_error_not_unsupported():
    assert not sa.is_unsupported_field_error(Exception("network timeout"))


# --- website_urls ----------------------------------------------------------

def test_website_urls_joins_multiple():
    item = SimpleNamespace(websites=[website(AutofillBehavior.NEVER),
                                     website(AutofillBehavior.NEVER)])
    item.websites[0].url = "https://a.example"
    item.websites[1].url = "https://b.example"
    assert sa.website_urls(item) == "https://a.example; https://b.example"


def test_website_urls_empty():
    assert sa.website_urls(SimpleNamespace(websites=[])) == ""


# --- write_report ----------------------------------------------------------

def test_write_report_csv(tmp_path):
    path = tmp_path / "skips.csv"
    skips = [{"vault": "V", "vault_id": "vid", "item_id": "iid",
              "title": "My, Item", "url": "https://e.example", "reason": "passkey"}]
    sa.write_report(str(path), "acc", skips)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == ["account", "vault", "vault_id", "item_id", "title", "url", "reason"]
    assert rows[1] == ["acc", "V", "vid", "iid", "My, Item", "https://e.example", "passkey"]


# --- backup write/read round-trip ------------------------------------------

def _row(item_id, url, behavior, title="A"):
    return {"vault": "V", "vault_id": "vid", "item_id": item_id, "title": title,
            "url": url, "behavior": behavior}


def test_backup_append_round_trip(tmp_path):
    path = tmp_path / "backup.csv"
    sa.append_backup(str(path), "acc", [_row("i1", "https://a.example", "AnywhereOnWebsite"),
                                        _row("i1", "https://a2.example", "Never")])
    parsed = sa.read_backup(str(path))
    assert parsed[("vid", "i1")]["urls"] == {
        "https://a.example": "AnywhereOnWebsite",
        "https://a2.example": "Never",
    }


def test_backup_append_is_cumulative_with_single_header(tmp_path):
    # simulates per-item flushes (and a resume): later appends must accumulate,
    # not overwrite, and only one header row may exist.
    path = tmp_path / "backup.csv"
    sa.append_backup(str(path), "acc", [_row("i1", "https://a.example", "AnywhereOnWebsite")])
    sa.append_backup(str(path), "acc", [_row("i2", "https://b.example", "Never", title="B")])
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == sa.BACKUP_HEADER
    assert sum(1 for r in rows if r == sa.BACKUP_HEADER) == 1
    parsed = sa.read_backup(str(path))
    assert set(parsed) == {("vid", "i1"), ("vid", "i2")}
    assert parsed[("vid", "i2")]["title"] == "B"


def test_backup_behaviors_are_valid_enum_values():
    # every behavior we record must round-trip back into the enum on revert
    from onepassword import AutofillBehavior
    for b in AutofillBehavior:
        assert AutofillBehavior(b.value) is b
