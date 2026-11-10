#!/usr/bin/env python3
"""Nazaré spectator forecast emails from Open-Meteo. Standard library only."""
import datetime as dt
import json
import os
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

LAT, LON = 39.60, -9.10  # Offshore approximation near Praia do Norte; not an inshore wave gauge.
TZ = ZoneInfo("Europe/Lisbon")
STATE = Path("state.json")
SOURCES = (
    "Marine: https://open-meteo.com/en/docs/marine-weather-api\n"
    "Weather: https://open-meteo.com/en/docs\n"
    "Independent verification: https://www.ipma.pt/ ; https://nazarewaves.com/\n"
)
# These are screening thresholds, NOT a scientific Nazaré wave-face prediction.
MIN_WAVE_M = float(os.getenv("MIN_WAVE_M", "3.5"))
MIN_PERIOD_S = float(os.getenv("MIN_PERIOD_S", "11"))
MIN_ALERT_SCORE = int(os.getenv("MIN_ALERT_SCORE", "3"))
UNTIL = dt.date(2026, 12, 8)

def fetch(base, hourly):
    q = urllib.parse.urlencode({
        "latitude": LAT, "longitude": LON, "hourly": ",".join(hourly),
        "timezone": "Europe/Lisbon", "forecast_days": 8,
    })
    req = urllib.request.Request(base + "?" + q, headers={"User-Agent": "NazareRadar/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)["hourly"]

def num(x):
    return float(x) if x is not None else None

def fmt(x, suffix="", digits=1):
    return "n/v" if x is None else f"{x:.{digits}f}{suffix}"

def assess(wave, swell, period, wind, rain, angle):
    if wave is None or period is None or wind is None:
        return -1, "DATEN FEHLEN"
    score = 0
    if wave >= MIN_WAVE_M: score += 2
    if wave >= 5: score += 1
    if period >= MIN_PERIOD_S: score += 1
    if period >= 14: score += 1
    if swell is not None and swell >= 3: score += 1
    if angle is not None and (angle >= 260 or angle <= 340 and angle >= 285):
        score += 1  # W-NW; coarse heuristic.
    if wind > 40: score -= 2
    elif wind > 27: score -= 1
    if rain is not None and rain > 2: score -= 1
    status = ("GRÜN (vorläufig)" if score >= 5 else "GELB" if score >= 3 else "ROT")
    # Explicitly avoid encouraging spectators during powerful storms.
    if wind > 45:
        status = "ROT – Starker Wind"
    return score, status

def records():
    marine = fetch(
        "https://marine-api.open-meteo.com/v1/marine",
        ["wave_height", "swell_wave_height", "swell_wave_period", "swell_wave_direction"],
    )
    weather = fetch(
        "https://api.open-meteo.com/v1/forecast",
        ["wind_speed_10m", "wind_direction_10m", "precipitation"],
    )
    weather_by_time = {t: i for i, t in enumerate(weather["time"])}
    items = []
    for i, timestamp in enumerate(marine["time"]):
        if timestamp not in weather_by_time:
            continue
        j = weather_by_time[timestamp]
        localtime = dt.datetime.fromisoformat(timestamp).replace(tzinfo=TZ)
        if not (8 <= localtime.hour <= 18):  # Daylight-oriented screening, seasonal sunset still matters.
            continue
        get_m = lambda key: num(marine[key][i])
        get_w = lambda key: num(weather[key][j])
        d = dict(t=localtime, wave=get_m("wave_height"),
                 swell=get_m("swell_wave_height"),
                 period=get_m("swell_wave_period"),
                 direction=get_m("swell_wave_direction"),
                 wind=get_w("wind_speed_10m"),
                 wind_dir=get_w("wind_direction_10m"),
                 rain=get_w("precipitation"))
        d["score"], d["status"] = assess(
            d["wave"], d["swell"], d["period"], d["wind"], d["rain"], d["direction"])
        items.append(d)
    return items

def best_by_day(items):
    result = {}
    for r in items:
        k = r["t"].date()
        if k not in result or r["score"] > result[k]["score"]:
            result[k] = r
    return sorted(result.values(), key=lambda r: r["t"])

def describe(r):
    return (f'{r["t"]:%a %d.%m., %H:%M} | {r["status"]} | '
            f'Wellenhöhe offshore {fmt(r["wave"], " m")}, '
            f'Swell {fmt(r["swell"], " m")}, Periode {fmt(r["period"], " s")}, '
            f'Swell-Richtung {fmt(r["direction"], "°", 0)}, '
            f'Wind {fmt(r["wind"], " km/h")} aus {fmt(r["wind_dir"], "°", 0)}, '
            f'Niederschlag {fmt(r["rain"], " mm/h")}')

def send(subject, body):
    sender = os.environ["SMTP_USER"]
    passwd = os.environ["SMTP_APP_PASSWORD"]
    recipients = [s.strip() for s in os.environ["EMAIL_TO"].split(",") if s.strip()]
    if not recipients:
        raise ValueError("EMAIL_TO is empty")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=25) as smtp:
        smtp.login(sender, passwd)
        smtp.send_message(msg)

def main():
    now = dt.datetime.now(TZ)
    if now.date() > UNTIL:
        print("Monitoring window completed.")
        return
    mode = os.getenv("MODE", "daily")
    days = best_by_day(records())
    if not days:
        raise RuntimeError("No overlapping forecast data")
    today = [r for r in days if r["t"].date() == now.date()]
    upcoming = [r for r in days if now.date() <= r["t"].date() <= now.date() + dt.timedelta(days=3)]
    ranked = sorted(days, key=lambda r: r["score"], reverse=True)[:3]
    disclaimer = (
        "\nWICHTIG: Die Zahlen sind modellierte signifikante OFFSHORE-Wellenhöhen, "
        "NICHT die Höhe einzelner brechender Nazaré-Wellen. Dies ist nur ein "
        "regelbasierter Frühindikator; Live-Webcam, IPMA-Warnungen und örtliche "
        "Bedingungen vor Fahrtantritt prüfen. Niemals auf exponierte Felsen "
        "oder in die Brandungszone gehen. 'GRÜN' garantiert keine Surf-Session.\n\n"
        + SOURCES)
    if mode == "daily":
        body = (f"Nazaré-Lagebericht vom {now:%d.%m.%Y %H:%M} (Lissabon)\n\n"
                + "HEUTE:\n" + ("\n".join(map(describe, today)) or "Kein Tagesfenster in den Daten.")
                + "\n\nKOMMENDE TAGE:\n" + "\n".join(map(describe, days))
                + "\n\nTOP 3 MODELLFENSTER:\n" + "\n".join(map(describe, ranked))
                + disclaimer)
        send(f"Nazaré Tagesbericht | {now:%d.%m.%Y}", body)
        print("Daily report sent.")
        return

    if mode != "alert":
        raise ValueError("MODE must be daily or alert")
    candidates = [r for r in upcoming if r["score"] >= MIN_ALERT_SCORE and
                  r["status"].startswith(("GRÜN", "GELB"))]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    # One advance warning per target date, followed by an optional day-of confirmation.
    to_send = []
    for r in candidates:
        is_today = r["t"].date() == now.date()
        key = f'{r["t"]:%Y-%m-%d}:{"today" if is_today else "advance"}'
        if key not in state:
            to_send.append((key, r, is_today))
    if not to_send:
        print("No new qualifying alert.")
        return
    lines = []
    for key, r, is_today in to_send:
        lines.append(("HEUTE PRÜFEN – " if is_today else "48–72H-VORWARNUNG / FRÜHSIGNAL – ")
                     + describe(r))
    body = (f"Nazaré Big-Wave-Radar | {now:%d.%m.%Y %H:%M}\n\n"
            + "\n".join(lines)
            + "\n\nVor einer spontanen Fahrt Webcam/amtliche Warnungen prüfen."
            + disclaimer)
    send("NAZARÉ BIG WAVE ALERT | Neue Modellfenster", body)
    for key, r, is_today in to_send:
        state[key] = now.isoformat()
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    print(f"Sent {len(to_send)} new alerts.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Radar error: {e}", file=sys.stderr)
        raise
