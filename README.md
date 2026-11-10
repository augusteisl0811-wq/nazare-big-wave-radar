# Nazaré Big-Wave-Radar – E-Mail-Automation

**Ziel:** Vom 10. November bis zum 8. Dezember 2026 erhalten du und deine Freunde
täglich einen Nazaré-Forecast und bei interessanten neuen Modellfenstern zusätzliche
Big-Wave-Frühwarnungen. Nach der Einrichtung läuft alles in GitHub Actions, auch wenn
dein Mac ausgeschaltet ist.

## 1. Enthaltene Dateien

```text
nazare-big-wave-radar/
├── README.md
├── radar.py
├── state.json
├── .gitignore
└── .github/workflows/radar.yml
```

- `radar.py`: Ruft Open-Meteo Marine und Weather ab, bewertet die Bedingungen
  und verschickt E-Mails per Gmail SMTP.
- `.github/workflows/radar.yml`: Täglicher Bericht um 08:00 Uhr (Portugal im November/
  Dezember) und separate Prüfung alle drei Stunden. GitHub-Scheduled-Jobs können
  verspätet starten und sind **keine garantierte Echtzeitüberwachung**.
- `state.json`: Merkt sich bereits versandte Alarmdaten und verhindert Standard-Duplikate.
  Neue Ereignisse/Änderungen **innerhalb desselben Tages** lösen in dieser einfachen
  Version nicht automatisch eine zweite Alarm-E-Mail aus.
- Am **8. Dezember 2026** ist Schluss; spätere Aufrufe machen nichts.

## 2. Einrichtung in VS Code / GitHub (ca. 15–25 Minuten)

1. Ordner in VS Code öffnen.
2. Kostenloses privates GitHub-Repository `nazare-big-wave-radar` erstellen.
3. Alle Dateien hochladen, **einschließlich des versteckten `.github`-Ordners**.
   Bei Terminal-Nutzung etwa:
   ```bash
   git init
   git add .
   git commit -m "Initial Nazaré radar"
   git branch -M main
   git remote add origin https://github.com/DEIN-NAME/nazare-big-wave-radar.git
   git push -u origin main
   ```
   Die `git remote`-URL anpassen; GitHub kann Authentifizierung verlangen.
4. In deinem Google-Konto **2‑Faktor-Authentifizierung** aktivieren, dann
   ein **Google App-Passwort** für dieses Skript erstellen:
   https://myaccount.google.com/apppasswords
   Das ist **nicht** dein normales Gmail-Passwort. Nicht bei jedem Konto ist
   diese Funktion verfügbar (z. B. manche Workspace-Konten).
5. Im GitHub-Repo: **Settings → Secrets and variables → Actions → New repository secret**.
   Diese drei Secrets hinzufügen:

   | Name | Beispiel/Wert |
   |---|---|
   | `SMTP_USER` | `meinname@gmail.com` |
   | `SMTP_APP_PASSWORD` | 16-stelliges Google-App-Passwort |
   | `EMAIL_TO` | `ich@example.com,freund1@example.com,freund2@example.com` |

   **Wichtig:** Keine echten E-Mail-Adressen oder Passwörter in `radar.py`
   oder direkt in den Workflow schreiben.
6. GitHub → **Actions → Nazare Big Wave Radar → Run workflow → daily**.
   E-Mail-Posteingang und Spam-Ordner prüfen. Danach optional
   einmal `alert` testen – dieser Modus schickt nur dann eine Mail, wenn
   ein neues qualifizierendes Modellfenster vorhanden ist.
7. Sicherstellen, dass GitHub Actions in den Repo-Einstellungen aktiv sind.
   Der Workflow benötigt Schreibrechte für `state.json`. Falls `git push`
   scheitert: **Settings → Actions → General → Workflow permissions →
   Read and write permissions** erlauben. Bei geschützten Branches
   ist eine andere Zustandsablage nötig.

## 3. Was steht in der E-Mail?

- **Jeden Tag:** Tageswert, die nächsten 8 Prognosetage, Top-3-Tagesfenster,
  signifikante modellierte Offshore-Wellenhöhe, Swellhöhe und -periode,
  Swellrichtung, Wind und Niederschlag.
- **Zusätzlicher Alarm:** Ein neues aussichtsreiches Modellfenster innerhalb
  der nächsten drei Tage und ggf. eine Meldung am Tag selbst.
- **ROT/GELB/GRÜN:** Grobe Heuristik als Entscheidungshilfe, keine
  meteorologische Qualitätsgarantie. Selbst 'GRÜN' heißt nicht, dass
  tatsächlich Giganten brechen oder Big-Wave-Surfer im Wasser sind.
- **Quellen:** Open-Meteo für die automatische Auswertung; IPMA und
  Nazaré Waves als Links zur manuellen Gegenprüfung.
  **Es erfolgt keine automatische Webcam-, IPMA- oder Surf-Session-Auswertung.**

### Physikalisch wichtiger Hinweis

`wave_height` bezeichnet eine **signifikante modellierte Wellenhöhe offshore**.
Sie ist **nicht** die Höhe der brechenden Wellen am Praia do Norte. Die
Bathymetrie des Nazaré-Canyons macht eine direkte Gleichsetzung falsch.
Auch die `swell_wave_period` ist ein Modellwert, keine Beobachtung vor Ort.

## 4. Grenzwerte ändern

In `radar.py` sind als Startwerte hinterlegt:
- Signifikante Wellenhöhe mindestens **3,5 m**
- Swellperiode mindestens **11 s**
- Mindest-Alarm-Score **3**

Das sind bewusst **experimentelle Screening-Werte** und keine
offiziellen Big-Wave-Schwellen. Eine fachliche Kalibrierung anhand
beobachteter Nazaré-Tage wäre sinnvoll.

## 5. Optional lokal testen

Benötigt Python 3.9+ und Internetzugang. Unter macOS/Linux:

```bash
export SMTP_USER="meinname@gmail.com"
export SMTP_APP_PASSWORD="DEIN_APP_PASSWORT"
export EMAIL_TO="ich@example.com,freund@example.com"
MODE=daily python3 radar.py
```

Das geht auch direkt im VS-Code-Terminal. Nicht versehentlich Terminal-Logs
mit Geheimnissen weitergeben.

## 6. Grenzen und mögliche Erweiterungen

- Cron-Zeiten sind **UTC**. Für diesen Zeitraum ist Portugal ebenfalls UTC.
  Bei Erweiterung auf den Sommer müsste man die Zeitumstellung beachten.
- Dieses Modell ist nur ein automatisierter Frühindikator; kein Live-Beobachter.
- GitHub Actions sind für private Repositories grundsätzlich nutzbar, aber
  Limits, mögliche Verzögerungen und Kontoeinstellungen gelten.
- Dieses einfache Skript erkennt neue Datumsfenster, nicht jede kurzfristige
  Korrektur einer bestehenden Wetterlage. Für präzise Änderungsalarme:
  Forecast-Snapshots speichern und Score-/Wind-Änderungen vergleichen.
- E-Mail funktioniert ohne zusätzliche kostenpflichtige Plattform,
  sofern Gmail SMTP/App-Passwort freigeschaltet sind und das Konto den
  Versand erlaubt.
- Für WhatsApp brauchst du eine gesonderte Integration (z. B. WhatsApp
  Business Platform mit Vorlagen/Einwilligungen).
- Falls du bereits ChatGPT-Aufgaben zu Nazaré nutzt: Diese laufen unabhängig;
  du bekommst womöglich ähnliche Meldungen zusätzlich in ChatGPT.

## Datenquellen

- https://open-meteo.com/en/docs/marine-weather-api
- https://open-meteo.com/en/docs
- https://www.ipma.pt/
- https://nazarewaves.com/

**Sicherheit:** Vor einem Ausflug aktuelle Warnungen, tatsächliche Brandung
und offizielle Sperrungen prüfen; niemals an exponierte Uferstellen gehen.
