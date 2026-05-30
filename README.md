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
  Concealed-Werte und **Passkeys** (empirisch verifiziert: WebAuthn-Login nach dem
  Edit weiterhin funktionsfähig).
- **Sicherheits-Skips**: Einträge mit nicht SDK-darstellbarem Feldtyp, Datei- oder
  Dokument-Anhang werden übersprungen und in eine Worklist geschrieben (`--report`).
- **Eine** Auth-Bestätigung pro Lauf (ein Prozess), nicht pro Eintrag.

**Betriebshinweis**: Bei großen Vaults Auto-Lock vorher hochsetzen, sonst brechen
die restlichen Schreibvorgänge ab. Dank Idempotenz kann der Lauf danach einfach
wiederholt werden.

#### Legacy-Items (nicht über das SDK editierbar) → Worklist + manuell

Ältere, im Browser gespeicherte Logins enthalten teils erfasste **Webformular-Felder**
(z.B. `realm`, `lang`, `saveusername`). Das SDK kann diesen Feldtyp nicht darstellen,
liefert ihn beim `get` nicht mit, und der Server **lehnt jede Bearbeitung** solcher
Items ab (`Editing is not supported for unsupported fields`). Diese Items werden
**sicher übersprungen** (kein Datenverlust) und beim `--apply` in eine CSV-Worklist
geschrieben (`--report`, Default `skipped_items.csv`).

**Warum kein automatischer Fix?** Das einzige Werkzeug, das diese Felder entfernen
könnte, ist `op item edit --template` – das **zerstört aber Passkeys** (empirisch
bestätigt). Und Passkeys sind über `op`, SDK **und** 1PUX **nicht erkennbar**, man
könnte betroffene Items also nicht vorab aussortieren. Vollautomatik ist für diese
Klasse daher nicht sicher möglich.

**Lösung:** Die Worklist-Items in der **1Password-Desktop-App** öffnen und das
Verhalten dort direkt setzen. Die App-GUI bearbeitet das Autofill-Verhalten **ohne**
Template und **ohne** Feldentfernung → Passkeys bleiben erhalten, kein Strippen nötig.

```bash
# Hauptlauf schreibt zugleich die Worklist
./.venv/bin/python set_autofill.py --account my.1password.eu --all-vaults \
    --apply --yes --report skipped.csv
```

## Tests

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest tests/ -q
```

Die Tests decken die reine Entscheidungslogik ab (welche Items geändert oder
übersprungen werden, Worklist-Ausgabe) und laufen **ohne** 1Password/Netzwerk.

## Hinweis zu Secrets

Item-Exporte (`*.json`) sind in `.gitignore` ausgeschlossen, da sie Zugangsdaten
enthalten können. Niemals Item-Dumps committen.
