# 1password-tools

Sammlung von Skripten zur Automatisierung von Aufgaben in 1Password, die über die
offizielle `op` CLI nicht (oder nur umständlich) abbildbar sind.

Die Skripte authentifizieren sich über die **1Password-Desktop-App** (`DesktopAuth`
aus dem Python-SDK) und erreichen damit **alle** Vaults des angemeldeten Nutzers –
inklusive des privaten Tresors, auf den Service Accounts keinen Zugriff haben.

## Voraussetzungen

- 1Password Desktop-App, **entsperrt**
- 1Password → Einstellungen → Entwickler → **„Integrate with other apps" = AN**
- 1Password CLI (`op`) für die Account-Auflistung
- Python 3.10+

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Skripte

### `set_autofill.py`

Setzt bei allen Login-/Password-Einträgen eines Vaults das **„Verhalten beim
automatischen Ausfüllen"** auf **„Nur genau für diesen Host"**
(SDK-Enum `AutofillBehavior.ExactDomain`). Dieses Feld ist über die `op` CLI
nicht erreichbar – nur über das SDK.

```bash
# Accounts auflisten
./.venv/bin/python set_autofill.py --list-accounts

# Vaults eines Accounts auflisten
./.venv/bin/python set_autofill.py --account my.1password.eu --list-vaults

# Probelauf (kein Schreiben)
./.venv/bin/python set_autofill.py --account my.1password.eu --vault "Mein Tresor"

# Tatsächlich schreiben
./.venv/bin/python set_autofill.py --account my.1password.eu --vault "Mein Tresor" --apply

# Alle Vaults eines Accounts, ohne Rückfrage
./.venv/bin/python set_autofill.py --account my.1password.eu --all-vaults --apply --yes
```

**Eigenschaften**

- **Idempotent**: Ein zweiter Lauf findet 0 zu ändernde Einträge.
- **Verlustfrei**: `get → put` erhält TOTP-Secrets, Custom-Felder, Sections,
  Concealed-Werte und (laut SDK-Release-Notes) Passkeys/Legacy-Felder.
- **Sicherheits-Skips**: Einträge mit nicht unterstütztem Feldtyp, Datei- oder
  Dokument-Anhang werden übersprungen und protokolliert.
- **Eine** Auth-Bestätigung pro Lauf (ein Prozess), nicht pro Eintrag.

**Betriebshinweis**: Bei großen Vaults Auto-Lock vorher hochsetzen, sonst brechen
die restlichen Schreibvorgänge ab. Dank Idempotenz kann der Lauf danach einfach
wiederholt werden.

## Hinweis zu Secrets

Item-Exporte (`*.json`) sind in `.gitignore` ausgeschlossen, da sie Zugangsdaten
enthalten können. Niemals Item-Dumps committen.
