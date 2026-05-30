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
  Sections. Operation ist **idempotent** (zweiter Lauf findet 0).
- **Backup/Undo**: `--apply` schreibt den Vorzustand jedes geänderten Items in eine Backup-CSV
  (`--backup`, inkrementell). `--revert <csv>` setzt exakt zurück (live verifiziert: ExactDomain →
  AnywhereOnWebsite). Geänderter Umfang ist nur `autofill_behavior` — minimaler Blast-Radius.
- **Robustheit**: Ein Vault ohne Zugriff (`you do not have the right permissions`) wird als
  `[VAULT SKIPPED]` geloggt und der Lauf läuft weiter (kein Abbruch bei `--all-vaults`).

## Passkeys (empirisch verifiziert, 2026-05-30)

- **SDK `items.put` ERHÄLT Passkeys**: nach `get→set autofill→put` auf einem Passkey-Item
  funktionierte der WebAuthn-Login weiterhin. → Der **Hauptpfad (SDK) ist passkey-sicher**;
  reine Passkey-Logins werden normal mitverarbeitet, der Passkey überlebt.
- **`op item edit --template` ZERSTÖRT Passkeys**: nach einem Template-Edit (gleiche sichtbare
  Felder) schlug der Login fehl. Bestätigt die Doku-Warnung. → Template-basierter Strip ist
  **NICHT** passkey-sicher.
- **Passkeys sind unsichtbar**: weder `op item get --format json` noch die SDK-`Item`-Sicht
  zeigen einen Passkey oder einen Marker. → Aus CLI/SDK **nicht erkennbar** (1PUX-Export enthält
  sie; das ist der einzige bekannte Erkennungsweg).
- Gefahr daher **nur** bei Items, die **gleichzeitig** Webformular-Müll **und** Passkey haben:
  Der SDK-`put` scheitert (Müll) → Strip-Pfad → Template zerstört den (unsichtbaren) Passkey.
  Reine Passkey-Items sind unkritisch. Wiederherstellung via Item-Versionsverlauf möglich.

## Legacy-/Webformular-Felder (empirisch verifiziert)

- Alte, im Browser gespeicherte Logins enthalten teils erfasste **Webformular-Felder**
  (leere `id`, Labels wie `realm`, `lang`, `saveusername`, `confirmpassword`, z.T. ganz leer).
- Das **SDK stellt diesen Feldtyp nicht dar** → beim `get` fehlen sie (nicht vorab erkennbar),
  beim `put` lehnt der **Server die gesamte Bearbeitung ab**:
  `invalid user input: … Editing is not supported for unsupported fields`.
  → `items.put` erhält Legacy-Felder also **nicht** transparent; betroffene Items sind schlicht
  nicht SDK-editierbar. (Korrigiert frühere Annahme aus den Release-Notes.)
- Das Skript fängt genau diesen Server-Fehler ab und zählt ihn als **skip** (kein Datenverlust —
  der `put` wird atomar abgelehnt, das Item bleibt unverändert).
- **Gezieltes Löschen scheitert**: `op item edit … 'label[delete]'` lehnt diese Felder ab
  (`cannot delete "…" because it is a built-in field`). Targeted-Delete funktioniert **nicht**.
- **Einziger funktionierender Strip = Template** (`op item edit --template`, leere-`id`-Felder
  herausgefiltert) — Treue für TOTP/Sections/Custom byte-genau bestätigt, **ABER zerstört Passkeys**.
- **Entscheidung (2026-05-30): kein automatischer Strip.** Vollautomatik ist für die Klasse
  „Müll-Feld + Passkey" beweisbar unsicher (Template zerstört Passkey, Passkey nicht erkennbar).
  Ein früher gebautes `--strip-legacy-fields` wurde **entfernt** (war ohnehin ein No-Op, da
  `label[delete]` scheitert). Stattdessen: **Worklist** (`--report`, CSV) listet alle
  übersprungenen Items; der Nutzer setzt sie **manuell in der Desktop-App** (GUI bearbeitet das
  Autofill-Verhalten direkt, ohne Template → passkey-sicher, kein Strippen nötig).
- **UI-Automation als Ausweg verworfen**: 1Password.app ist nicht AppleScript-fähig (sdef -192),
  Accessibility-Scripting verweigert (-25211).

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
