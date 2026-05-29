# 1Password Autofill-Bulk-Edit

Tooling, um bei allen Login-/Password-Einträgen das **„Verhalten beim automatischen
Ausfüllen"** auf **„Nur genau für diesen Host"** zu setzen.

## Kernerkenntnisse (empirisch verifiziert)

- Die **`op` CLI kann dieses Feld NICHT** lesen/schreiben — es ist nicht im CLI-Item-Schema.
  Templates/Assignments verwerfen es stillschweigend. (Bestätigt durch manuelles Setzen +
  erneutes Auslesen: das Feld taucht im CLI-JSON nicht auf.) → CLI-Weg ist tot.
- Das **Python-SDK kann es**: `website.autofill_behavior`. Setzen via `items.get → modify → items.put`.
- Ziel-Enum: **`AutofillBehavior.EXACTDOMAIN`** (Wert `"ExactDomain"`) = „Nur genau für diesen Host".
  Weitere Werte: `ANYWHEREONWEBSITE` (Default), `NEVER`. (Doku nennt teils „ExactMatch" — falsch.)
- **Auth über `DesktopAuth`**, nicht Service Account. Grund: Service Accounts haben **keinen Zugriff
  auf den Private-Vault** (~98% der privaten Items). DesktopAuth nutzt die Desktop-App-Session und
  erreicht **alle** Vaults inkl. Private.
- **Round-Trip-Treue bestätigt**: `get→put` erhält TOTP-Secret, Custom-Felder, Concealed-Werte,
  Sections. Laut SDK-Release-Notes erhält `items.put` auch **Passkeys/Legacy-Felder** (anders als
  CLI-Templates). Operation ist **idempotent** (zweiter Lauf findet 0).

## Voraussetzungen

1. 1Password Desktop → Einstellungen → Entwickler → **„Integrate with other apps" = AN**
   (zusätzlich zur CLI-Integration).
2. Die App muss **entsperrt** sein, sonst: „Denied authorization for SDK client".
3. Python-venv mit SDK: `./.venv` (Paket `onepassword-sdk`).

## Nutzung

```bash
./.venv/bin/python set_autofill.py --list-accounts
./.venv/bin/python set_autofill.py --account my.1password.eu --list-vaults
# Probelauf (kein Schreiben):
./.venv/bin/python set_autofill.py --account my.1password.eu --vault "Mein Tresor"
# Tatsächlich schreiben:
./.venv/bin/python set_autofill.py --account my.1password.eu --vault "Mein Tresor" --apply
# Alle Vaults eines Accounts:
./.venv/bin/python set_autofill.py --account my.1password.eu --all-vaults --apply --yes
```

- `--account` ist die URL aus `--list-accounts` (z.B. `my.1password.eu`).
- **Vault-Namen wie in `--list-vaults`** verwenden — der Private-Vault kann im SDK
  einen abweichenden, frei gewählten Namen haben (nicht zwingend „Private").
- **Eine** Auth-Bestätigung pro Lauf (ein Prozess), nicht pro Item.

## Betriebshinweise

- **Auto-Lock**: Bei großen Vaults (mehrere tausend Items, ~30–60 Min) Auto-Lock vorher hochsetzen,
  sonst brechen die restlichen Schreibvorgänge ab. Wegen Idempotenz kann man danach einfach erneut laufen lassen.
- **Übersprungen** werden Items mit nicht unterstütztem Feld (z.B. Passkey), Datei- oder
  Dokument-Anhang (`risky_reason()` in `set_autofill.py`) — werden geloggt; ggf. manuell prüfen.
- Vor großem Lauf zuerst einen mittleren Vault messen, um die Dauer abzuschätzen.

## Größenordnung

- Private Tresore können mehrere tausend Login-Items enthalten — entsprechend lange
  Laufzeit (~30–60 Min) und Auto-Lock beachten. Business-Accounts verteilen sich oft
  auf viele geteilte Vaults; `--all-vaults` erfasst sie in einem Lauf.
