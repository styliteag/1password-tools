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

#### Legacy-Items (nicht über das SDK editierbar)

Ältere, im Browser gespeicherte Logins enthalten teils erfasste **Webformular-Felder**
(z.B. `realm`, `lang`, `saveusername`). Das SDK kann diesen Feldtyp nicht darstellen,
liefert ihn beim `get` nicht mit, und der Server **lehnt jede Bearbeitung** solcher
Items ab (`Editing is not supported for unsupported fields`). Diese Items werden
standardmäßig **sicher übersprungen** – nichts wird beschädigt.

Mit `--strip-legacy-fields` lassen sich diese Felder **vor** dem Edit entfernen:

```bash
./.venv/bin/python set_autofill.py --account my.1password.eu --vault "My Vault" \
    --apply --strip-legacy-fields
```

- **Passkey-sicher**: nutzt gezielte Feld-Löschungen über die `op` CLI
  (`op item edit … 'label[delete]'`), **nie** ein JSON-Template (Templates würden
  Passkeys überschreiben).
- **Verlustbehaftet**: Username/Passwort/TOTP/Notizen bleiben erhalten, die
  Formular-Vorbelegungen (z.B. `realm`) gehen verloren. Reversibel über den
  **Versionsverlauf** des Items.
- Items mit **unbenannten** oder **doppelt benannten** Legacy-Feldern werden nicht
  automatisch behandelt, sondern zur manuellen Prüfung gemeldet.

> Hinweis: Das `--strip-legacy-fields`-Verfahren mit gezielten `op`-Löschungen ist
> bislang nicht in einem echten Lauf gegengetestet. Vor breitem Einsatz an **einem**
> Item verifizieren.

## Tests

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest tests/ -q
```

Die Tests decken die reine Entscheidungslogik ab (welche Items geändert,
übersprungen oder gestrippt werden) und laufen **ohne** 1Password/Netzwerk.

## Hinweis zu Secrets

Item-Exporte (`*.json`) sind in `.gitignore` ausgeschlossen, da sie Zugangsdaten
enthalten können. Niemals Item-Dumps committen.
