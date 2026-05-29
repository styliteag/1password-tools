"""Offline unit tests for the pure logic of set_autofill.py.

These tests do not touch 1Password, the SDK, or the network. They cover the
decision logic that determines which items are edited, skipped, or stripped.
"""
from __future__ import annotations

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


# --- plan_legacy_strip -----------------------------------------------------

def test_strip_plan_all_named_fields():
    item = {"fields": [
        {"id": "username", "label": "username"},
        {"id": "password", "label": "password"},
        {"id": "", "label": "realm"},
        {"id": "", "label": "lang"},
    ]}
    labels, blocker = sa.plan_legacy_strip(item)
    assert blocker is None
    assert labels == ["realm", "lang"]


def test_strip_plan_blocks_unnamed_field():
    item = {"fields": [{"id": "", "label": "realm"}, {"id": "", "label": None}]}
    labels, blocker = sa.plan_legacy_strip(item)
    assert labels == []
    assert "unnamed" in blocker


def test_strip_plan_blocks_duplicate_labels():
    item = {"fields": [{"id": "", "label": "x"}, {"id": "", "label": "x"}]}
    labels, blocker = sa.plan_legacy_strip(item)
    assert labels == []
    assert "duplicate" in blocker


def test_strip_plan_nothing_to_remove():
    item = {"fields": [{"id": "username", "label": "username"}]}
    labels, blocker = sa.plan_legacy_strip(item)
    assert labels == []
    assert blocker is not None


def test_strip_plan_keeps_totp_removes_empty():
    item = {"fields": [
        {"id": "TOTP_x", "label": "one-time password"},
        {"id": "", "label": "realm"},
    ]}
    labels, blocker = sa.plan_legacy_strip(item)
    assert blocker is None
    assert labels == ["realm"]
