#!/usr/bin/env python3
"""Set the autofill behavior of every Login/Password item in a vault to
"Only fill on this exact host" (SDK enum: AutofillBehavior.ExactDomain).

Authentication goes through the 1Password desktop app (DesktopAuth) and therefore
has access to ALL vaults including the private one. Requirements:
  1Password -> Settings -> Developer -> "Integrate with other apps" = ON
  The app must be unlocked, otherwise: "Denied authorization for SDK client".

Some old logins carry fields the SDK cannot represent (captured web-form fields,
"Sign in with Google/Apple" fields, passkeys). The server rejects editing those
items, so they are skipped atomically (no data loss) and written to a worklist
(--report). Set their autofill behavior by hand in the desktop app: the GUI edits
it directly without a template, so it preserves passkeys and needs no field removal.

Examples:
  python set_autofill.py --list-accounts
  python set_autofill.py --account my.1password.eu --list-vaults
  python set_autofill.py --account my.1password.eu --vault "My Vault"          # dry run
  python set_autofill.py --account my.1password.eu --vault "My Vault" --apply  # writes
  python set_autofill.py --account my.1password.eu --all-vaults --apply --yes
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import subprocess
import sys

from onepassword import (
    AutofillBehavior,
    Client,
    DesktopAuth,
    ItemCategory,
    ItemFieldType,
    ItemState,
    Website,
)

INTEGRATION_NAME = "autofill-bulk-edit"
INTEGRATION_VERSION = "1.0.0"
TARGET = AutofillBehavior.EXACTDOMAIN
WEBSITE_CATEGORIES = {ItemCategory.LOGIN, ItemCategory.PASSWORD}
DEFAULT_REPORT = "skipped_items.csv"


def log(msg: str) -> None:
    print(msg, flush=True)


def list_accounts() -> int:
    """Print the locally known 1Password accounts (via the op CLI)."""
    res = subprocess.run(
        ["op", "account", "list"], capture_output=True, text=True
    )
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        log("\nError: 'op account list' failed. Is the 1Password CLI installed?")
    else:
        log("\nUse the value from the URL column as --account (e.g. my.1password.eu).")
    return res.returncode


async def authenticate(account: str, retries: int = 3) -> Client:
    """Establish a DesktopAuth connection (with retry in case the app is locked)."""
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await Client.authenticate(
                auth=DesktopAuth(account_name=account),
                integration_name=INTEGRATION_NAME,
                integration_version=INTEGRATION_VERSION,
            )
        except Exception as err:  # noqa: BLE001 - SDK raises generic errors
            last = err
            log(f"  Auth attempt {attempt}/{retries} failed: {err}")
            if attempt < retries:
                log("  Unlock 1Password and confirm the authorization prompt if shown ...")
                await asyncio.sleep(6)
    raise SystemExit(
        f"Could not authenticate for '{account}': {last}\n"
        "Check: app unlocked? 'Integrate with other apps' enabled? account name correct?"
    )


async def resolve_vaults(client: Client, vault: str | None, all_vaults: bool):
    """Return a list of (id, title) for the vaults to process."""
    overviews = await client.vaults.list()
    if all_vaults:
        return [(v.id, v.title) for v in overviews]

    by_id = {v.id: v for v in overviews}
    if vault in by_id:
        return [(vault, by_id[vault].title)]
    exact = [v for v in overviews if v.title == vault]
    ci = [v for v in overviews if v.title.lower() == (vault or "").lower()]
    matches = exact or ci
    if len(matches) == 1:
        return [(matches[0].id, matches[0].title)]
    if not matches:
        raise SystemExit(f"Vault '{vault}' not found. Check with --list-vaults.")
    raise SystemExit(
        f"Vault name '{vault}' is ambiguous ({len(matches)} matches). "
        "Please pass the vault ID instead of the name."
    )


def overview_needs_change(overview) -> bool:
    """True if the item has a website whose behavior is not yet the target."""
    if overview.category not in WEBSITE_CATEGORIES:
        return False
    if getattr(overview, "state", ItemState.ACTIVE) != ItemState.ACTIVE:
        return False
    return any(w.autofill_behavior != TARGET for w in overview.websites)


def risky_reason(item) -> str | None:
    """Reason why an item is skipped before attempting a put (visible markers).

    Note: most legacy/unsupported fields (captured web-form fields, passkeys) are
    NOT surfaced by the SDK on get, so they cannot be detected here. Those surface
    only when the server rejects the put; that case is handled in process_vault.
    """
    if any(f.field_type == ItemFieldType.UNSUPPORTED for f in item.fields):
        return "unsupported field (e.g. passkey)"
    if item.files:
        return "file attachment"
    if item.document is not None:
        return "document attachment"
    return None


def is_unsupported_field_error(err: Exception) -> bool:
    """True if the server rejected the edit because of hidden unsupported fields.

    Such items carry fields the SDK does not represent (captured web-form inputs,
    'Sign in with Google/Apple' fields, passkeys). The put is rejected atomically,
    so the item is left untouched. We treat this as a clean skip, not a failure.
    The message does not distinguish a passkey from web-form junk, so these items
    must be handled by hand in the desktop app (see module docstring).
    """
    msg = str(err).lower()
    return "unsupported field" in msg or "not supported for unsupported" in msg


def website_urls(item) -> str:
    """Join an item's website URLs for the worklist (helps locate it in the app)."""
    return "; ".join(w.url for w in item.websites if w.url)


def apply_target(item):
    """Set the target behavior on all websites of the item (new objects)."""
    item.websites = [
        Website(url=w.url, label=w.label, autofill_behavior=TARGET)
        for w in item.websites
    ]
    return item


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def write_report(path: str, account: str, skips: list[dict]) -> None:
    """Write the worklist of skipped items to a CSV for manual GUI handling."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["account", "vault", "vault_id", "item_id", "title", "url", "reason"])
        for s in skips:
            writer.writerow([account, s["vault"], s["vault_id"], s["item_id"],
                             s["title"], s["url"], s["reason"]])


async def list_vaults(account: str) -> None:
    client = await authenticate(account)
    vaults = await client.vaults.list()
    log(f"{'VAULT-ID':<28}  NAME")
    for v in sorted(vaults, key=lambda x: x.title.lower()):
        log(f"{v.id:<28}  {v.title}")


async def process_vault(client: Client, vault_id: str, title: str, apply: bool) -> dict:
    """Process a single vault. Returns a stats dict (incl. a 'skips' worklist)."""
    overviews = await client.items.list(vault_id)
    candidates = [o for o in overviews if overview_needs_change(o)]
    stats = {"vault": title, "scanned": len(overviews), "to_change": len(candidates),
             "changed": 0, "skipped": 0, "failed": 0, "skips": []}
    log(f"\n=== Vault '{title}' ({vault_id}) ===")
    log(f"  {len(overviews)} items scanned, {len(candidates)} need changes.")

    if not apply:
        log(f"  Dry run: up to {len(candidates)} would be changed. Items carrying "
            "legacy/unsupported fields (passkeys, captured web-form fields) are not "
            "SDK-editable and will be skipped (and worklisted) on --apply.")
        return stats

    def record_skip(item, item_id, reason):
        stats["skipped"] += 1
        stats["skips"].append({
            "vault": title, "vault_id": vault_id, "item_id": item_id,
            "title": item.title, "url": website_urls(item), "reason": reason,
        })

    for idx, ov in enumerate(candidates, 1):
        item = await client.items.get(vault_id, ov.id)
        reason = risky_reason(item)
        if reason:
            record_skip(item, ov.id, reason)
            log(f"  [SKIP] {item.title!r}: {reason}")
            continue
        apply_target(item)
        try:
            await client.items.put(item)
            stats["changed"] += 1
        except Exception as err:  # noqa: BLE001
            if is_unsupported_field_error(err):
                record_skip(item, ov.id, "not SDK-editable (web-form field or passkey)")
                log(f"  [SKIP] {item.title!r}: not SDK-editable (handle in app)")
            else:
                stats["failed"] += 1
                log(f"  [ERROR] {item.title!r}: {err}")
        if idx % 25 == 0:
            log(f"  ... {idx}/{len(candidates)} processed")

    log(f"  Result: {stats['changed']} changed, "
        f"{stats['skipped']} skipped, {stats['failed']} failed.")
    return stats


async def run_edit(account: str, vault: str | None, all_vaults: bool,
                   apply: bool, assume_yes: bool, report_path: str) -> None:
    client = await authenticate(account)
    targets = await resolve_vaults(client, vault, all_vaults)

    log(f"Account : {account}")
    log(f"Mode    : {'WRITE (--apply)' if apply else 'DRY RUN (no writes)'}")
    log(f"Target  : autofill behavior = 'Only fill on this exact host' (ExactDomain)")
    log(f"Vaults  : {', '.join(t for _, t in targets)}")

    if apply and not assume_yes:
        if not confirm(f"\nReally write to {len(targets)} vault(s)? [y/N] "):
            log("Aborted.")
            return

    totals = {"changed": 0, "skipped": 0, "failed": 0, "to_change": 0}
    all_skips: list[dict] = []
    vault_errors: list[tuple[str, str]] = []
    for vault_id, title in targets:
        try:
            s = await process_vault(client, vault_id, title, apply)
        except Exception as err:  # noqa: BLE001 - one bad vault must not abort the run
            vault_errors.append((title, str(err)))
            log(f"\n=== Vault '{title}' ({vault_id}) ===")
            log(f"  [VAULT SKIPPED] {err}")
            continue
        for k in totals:
            totals[k] += s.get(k, 0)
        all_skips.extend(s["skips"])

    log("\n==================== TOTAL ====================")
    if apply:
        log(f"  Changed: {totals['changed']} | Skipped: {totals['skipped']} | Failed: {totals['failed']}")
        if all_skips:
            write_report(report_path, account, all_skips)
            log(f"\n  {len(all_skips)} item(s) need manual handling -> worklist: {report_path}")
            log("  Open each in the 1Password desktop app and set 'Only fill on this")
            log("  exact host' directly (the GUI preserves passkeys; no stripping needed).")
    else:
        log(f"  Would change: {totals['to_change']} items")
        log("  Run again with --apply to actually write (and produce the skip worklist).")

    if vault_errors:
        log(f"\n  {len(vault_errors)} vault(s) skipped entirely (e.g. no access):")
        for title, err in vault_errors:
            log(f"    - {title}: {err}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Set the autofill behavior of all Login/Password items in a "
                    "vault to 'Only fill on this exact host'.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--list-accounts", action="store_true",
                   help="List known 1Password accounts and exit.")
    p.add_argument("--account", help="Account (URL/shorthand/email, see --list-accounts).")
    p.add_argument("--list-vaults", action="store_true",
                   help="List the vaults of the account and exit.")
    p.add_argument("--vault", help="Vault name or vault ID to process.")
    p.add_argument("--all-vaults", action="store_true",
                   help="Process all vaults of the account (instead of --vault).")
    p.add_argument("--apply", action="store_true",
                   help="Actually write changes (otherwise dry run only).")
    p.add_argument("--yes", action="store_true",
                   help="Skip the confirmation prompt on --apply.")
    p.add_argument("--report", default=DEFAULT_REPORT, metavar="PATH",
                   help=f"CSV worklist of skipped (not SDK-editable) items, written "
                        f"on --apply (default: {DEFAULT_REPORT}). Handle these by "
                        f"hand in the desktop app.")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.list_accounts:
        return list_accounts()

    if not args.account:
        log("Error: --account is required (or --list-accounts).")
        return 2

    if args.list_vaults:
        asyncio.run(list_vaults(args.account))
        return 0

    if not args.vault and not args.all_vaults:
        log("Error: --vault <name|id> or --all-vaults is required.")
        return 2

    asyncio.run(run_edit(args.account, args.vault, args.all_vaults,
                         args.apply, args.yes, args.report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
