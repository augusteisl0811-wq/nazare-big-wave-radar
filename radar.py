
#!/usr/bin/env python3
"""Nazaré Big-Wave-Radar – HTML E-Mail Edition."""

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
from html import escape


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

LAT = 39.60
LON = -9.10

TZ = ZoneInfo("Europe/Lisbon")
STATE = Path("state.json")

UNTIL = dt.date(2026, 12, 8)

MIN_WAVE_M = float(os.getenv("MIN_WAVE_M", "3.5"))
MIN_PERIOD_S = float(os.getenv("MIN_PERIOD_S", "11"))
MIN_ALERT_SCORE = int(os.getenv("MIN_ALERT_SCORE", "3"))

COLORS = {
    "navy": "#102539",
    "blue": "#2563eb",
    "green": "#16865b",
    "yellow": "#b7791f",
    "red": "#dc3545",
    "background": "#f2f5f9",
    "text": "#172b3a",
    "muted": "#64748b",
    "border": "#e2e8f0",
}

SOURCES = """
Open-Meteo Marine:
https://open-meteo.com/en/docs/marine-weather-api

Open-Meteo Weather:
https://open-meteo.com/en/docs

IPMA:
https://www.ipma.pt/

Nazaré Waves:
https://nazarewaves.com/
"""


# --------------------------------------------------
# DATA
# --------------------------------------------------

def fetch(base, hourly):
    params = urllib.parse.urlencode({
        "latitude": LAT,
        "longitude": LON,
        "hourly": ",".join(hourly),
        "timezone": "Europe/Lisbon",
        "forecast_days": 8,
    })

    url = base + "?" + params

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NazareRadar/2.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["hourly"]


def num(value):
    return float(value) if value is not None else None


def fmt(value, unit="", digits=1):
    if value is None:
        return "n/v"
    return f"{value:.{digits}f}{unit}"


def assess(wave, swell, period, wind, rain, direction):
    """Experimental screening score, not a surf-face forecast."""

    if wave is None or period is None or wind is None:
        return -1, "DATEN FEHLEN"

    score = 0

    if wave >= MIN_WAVE_M:
        score += 2

    if wave >= 5:
        score += 1

    if period >= MIN_PERIOD_S:
        score += 1

    if period >= 14:
        score += 1

    if swell is not None and swell >= 3:
        score += 1

    if direction is not None and 260 <= direction <= 340:
        score += 1

    if wind > 40:
        score -= 2
    elif wind > 27:
        score -= 1

    if rain is not None and rain > 2:
        score -= 1

    if wind > 45:
        return score, "ROT – STARKER WIND"

    if score >= 5:
        return score, "GRÜN"

    if score >= 3:
        return score, "GELB"

    return score, "ROT"


def records():
    marine = fetch(
        "https://marine-api.open-meteo.com/v1/marine",
        [
            "wave_height",
            "swell_wave_height",
            "swell_wave_period",
            "swell_wave_direction",
        ],
    )

    weather = fetch(
        "https://api.open-meteo.com/v1/forecast",
        [
            "wind_speed_10m",
            "wind_direction_10m",
            "precipitation",
        ],
    )

    weather_times = {
        t: i for i, t in enumerate(weather["time"])
    }

    items = []

    for i, timestamp in enumerate(marine["time"]):

        if timestamp not in weather_times:
            continue

        j = weather_times[timestamp]

        localtime = dt.datetime.fromisoformat(
            timestamp
        ).replace(tzinfo=TZ)

        # Daytime-oriented screening.
        # This is not a sunrise/sunset calculation.
        if not 8 <= localtime.hour <= 17:
            continue

        def m(key):
            return num(marine[key][i])

        def w(key):
            return num(weather[key][j])

        item = {
            "t": localtime,
            "wave": m("wave_height"),
            "swell": m("swell_wave_height"),
            "period": m("swell_wave_period"),
            "direction": m("swell_wave_direction"),
            "wind": w("wind_speed_10m"),
            "wind_dir": w("wind_direction_10m"),
            "rain": w("precipitation"),
        }

        item["score"], item["status"] = assess(
            item["wave"],
            item["swell"],
            item["period"],
            item["wind"],
            item["rain"],
            item["direction"],
        )

        items.append(item)

    return items


def best_by_day(items, now):
    """Select best remaining forecast hour per day."""

    best = {}

    for item in items:

        if item["t"] < now:
            continue

        date = item["t"].date()

        if date not in best:
            best[date] = item

        elif item["score"] > best[date]["score"]:
            best[date] = item

    return sorted(
        best.values(),
        key=lambda r: r["t"]
    )


# --------------------------------------------------
# VISUAL COMPONENTS
# --------------------------------------------------

def status_style(status):

    if status.startswith("GRÜN"):
        return "#e4f7ec", "#16865b", "GUTE MODELLBEDINGUNGEN"

    if status.startswith("GELB"):
        return "#fff3d6", "#a76c11", "POTENZIAL"

    if status.startswith("ROT"):
        return "#fde8e8", "#c53030", "EHER UNGEEIGNET"

    return "#edf2f7", "#64748b", "DATEN FEHLEN"


def badge(status):

    bg, fg, label = status_style(status)

    return f"""
    <span style="
        display:inline-block;
        background:{bg};
        color:{fg};
        border-radius:30px;
        padding:7px 12px;
        font-size:11px;
        font-weight:700;
        letter-spacing:0.4px;
    ">
        {escape(label)}
    </span>
    """


def metric(label, value):

    return f"""
    <td style="
        width:33%;
        padding:12px 7px;
        text-align:center;
        vertical-align:top;
    ">
        <div style="
            font-size:10px;
            color:#64748b;
            letter-spacing:0.5px;
            text-transform:uppercase;
            margin-bottom:7px;
        ">
            {escape(label)}
        </div>

        <div style="
            font-size:21px;
            font-weight:700;
            color:#102539;
        ">
            {escape(value)}
        </div>
    </td>
    """


def day_card(r, featured=False):

    date = r["t"].strftime("%d.%m.%Y")
    time = r["t"].strftime("%H:%M")

    weekdays = [
        "Montag", "Dienstag", "Mittwoch",
        "Donnerstag", "Freitag",
        "Samstag", "Sonntag"
    ]

    day_name = weekdays[r["t"].weekday()]

    weekend = r["t"].weekday() >= 5

    weekend_text = (
        '<span style="color:#2563eb;font-size:11px;'
        'font-weight:700;"> WOCHENENDE</span>'
        if weekend else ""
    )

    border = (
        "2px solid #2563eb"
        if featured else "1px solid #e2e8f0"
    )

    return f"""
    <div style="
        background:#ffffff;
        border:{border};
        border-radius:14px;
        margin-bottom:14px;
        overflow:hidden;
    ">

        <div style="
            padding:16px 17px;
            border-bottom:1px solid #edf2f7;
        ">

            <div style="
                font-size:16px;
                font-weight:700;
                color:#102539;
                margin-bottom:8px;
            ">
                {day_name}, {date}
                {weekend_text}
            </div>

            <div style="margin-bottom:8px;">
                {badge(r["status"])}
            </div>

            <div style="font-size:12px;color:#64748b;">
                Bestes Modellfenster: ca. {time} Uhr
            </div>

        </div>

        <table role="presentation"
               width="100%"
               cellpadding="0"
               cellspacing="0"
               style="table-layout:fixed;">

            <tr>
                {metric("Offshore-Wellen", fmt(r["wave"], " m"))}
                {metric("Swellperiode", fmt(r["period"], " s"))}
                {metric("Wind", fmt(r["wind"], " km/h"))}
            </tr>

        </table>

        <div style="
            background:#f8fafc;
            padding:12px 16px;
            font-size:12px;
            line-height:1.8;
            color:#475569;
        ">
            Swell: <strong>{fmt(r["swell"], " m")}</strong>
            &nbsp; | &nbsp;
            Richtung: <strong>{fmt(r["direction"], "°", 0)}</strong>
            <div>
                Wind aus {fmt(r["wind_dir"], "°", 0)}
                &nbsp; · &nbsp;
                Regen: {fmt(r["rain"], " mm/h")}
            </div>
        </div>

    </div>
    """


def section_title(text):

    return f"""
    <h2 style="
        font-size:18px;
        font-weight:700;
        color:#102539;
        margin:28px 0 14px;
    ">
        {escape(text)}
    </h2>
    """


def email_layout(subtitle, content, now):

    date = now.strftime("%d.%m.%Y")
    time = now.strftime("%H:%M")

    return f"""<!DOCTYPE html>
<html lang="de">

<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0">
<title>Nazaré Big-Wave-Radar</title>
</head>

<body style="
    margin:0;
    padding:0;
    background:#f2f5f9;
    font-family:Arial,Helvetica,sans-serif;
    color:#172b3a;
">

<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       style="background:#f2f5f9;">

<tr>
<td align="center" style="padding:20px 10px;">

<table role="presentation"
       width="100%"
       cellpadding="0"
       cellspacing="0"
       style="
           max-width:620px;
           background:#ffffff;
           border-radius:18px;
           overflow:hidden;
       ">

<tr>
<td style="
    background:#102539;
    padding:32px 25px;
    color:#ffffff;
">

<div style="
    font-size:11px;
    letter-spacing:2px;
    color:#a8c7df;
    font-weight:700;
    margin-bottom:11px;
">
    NAZARÉ · PORTUGAL
</div>

<div style="
    font-size:30px;
    font-weight:800;
    line-height:1.15;
    margin-bottom:9px;
">
    BIG WAVE<br>RADAR.
</div>

<div style="
    font-size:14px;
    color:#c9d9e7;
    line-height:1.6;
">
    {escape(subtitle)}
</div>

<div style="
    margin-top:19px;
    font-size:12px;
    color:#a8c7df;
">
    {date} · {time} Uhr · Lisbon Time
</div>

</td>
</tr>

<tr>
<td style="padding:23px 20px;">

{content}

<div style="
    margin-top:27px;
    padding:17px;
    border-radius:12px;
    background:#f1f5f9;
    font-size:12px;
    line-height:1.75;
    color:#475569;
">

<strong>Wichtig zur Interpretation</strong>

<p style="margin:8px 0 0;">
Die angegebenen Wellenhöhen sind modellierte,
signifikante Offshore-Wellenhöhen.
Sie entsprechen nicht der tatsächlichen Höhe
einzelner brechender Wellen vor Nazaré.
</p>

<p style="margin:8px 0 0;">
Die Bewertung ist ein experimenteller
Frühindikator, keine bestätigte
Big-Wave-Surf-Prognose.
Vor einem Ausflug Webcam, amtliche
Warnungen und lokale Bedingungen prüfen.
Exponierte Felsen und Brandungszonen meiden.
</p>

</div>

<div style="
    margin-top:26px;
    padding-top:18px;
    border-top:1px solid #e2e8f0;
    text-align:center;
    font-size:12px;
    line-height:2;
    color:#64748b;
">

<strong>FORECAST & LIVE CHECK</strong><br>

<a href="https://nazarewaves.com/"
   style="color:#2563eb;">
   Nazaré Waves
</a>

&nbsp; · &nbsp;

<a href="https://www.ipma.pt/"
   style="color:#2563eb;">
   IPMA
</a>

&nbsp; · &nbsp;

<a href="https://open-meteo.com/en/docs/marine-weather-api"
   style="color:#2563eb;">
   Marine Data
</a>

<div style="margin-top:13px;color:#94a3b8;">
    NAZARÉ BIG WAVE RADAR · AUTOMATED REPORT
</div>

</div>

</td>
</tr>
</table>

</td>
</tr>
</table>

</body>
</html>
"""


# --------------------------------------------------
# TEXT FALLBACK
# --------------------------------------------------

def describe(r):

    return (
        f'{r["t"]:%d.%m.%Y %H:%M} | '
        f'{r["status"]} | '
        f'Offshore {fmt(r["wave"], " m")} | '
        f'Swell {fmt(r["swell"], " m")} | '
        f'Periode {fmt(r["period"], " s")} | '
        f'Wind {fmt(r["wind"], " km/h")}'
    )


DISCLAIMER = (
    "\n\nOffshore-Wellenhöhe ist nicht die Höhe "
    "brechender Nazaré-Wellen. "
    "Bewertung nur als Modell-Frühindikator. "
    "Aktuelle Warnungen und Webcams prüfen.\n\n"
    + SOURCES
)


# --------------------------------------------------
# EMAIL SENDER
# --------------------------------------------------

def send(subject, text_body, html_body):

    sender = os.environ["SMTP_USER"]
    password = os.environ["SMTP_APP_PASSWORD"]

    recipients = [
        address.strip()
        for address in os.environ["EMAIL_TO"].split(",")
        if address.strip()
    ]

    if not recipients:
        raise ValueError("EMAIL_TO is empty")

    message = EmailMessage()

    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject

    message.set_content(text_body)

    message.add_alternative(
        html_body,
        subtype="html"
    )

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        context=ssl.create_default_context(),
        timeout=30,
    ) as smtp:

        smtp.login(sender, password)
        smtp.send_message(message)


# --------------------------------------------------
# DAILY REPORT
# --------------------------------------------------

def daily_report(days, now):

    today = [
        r for r in days
        if r["t"].date() == now.date()
    ]

    ranked = sorted(
        days,
        key=lambda r: r["score"],
        reverse=True
    )[:3]

    next_days = [
        r for r in days
        if r["t"].date() > now.date()
    ]

    today_html = (
        day_card(today[0], featured=True)
        if today
        else "<p>Für heute kein verbleibendes Tagesfenster.</p>"
    )

    best_html = "".join(
        day_card(r, featured=True)
        for r in ranked
    )

    forecast_html = "".join(
        day_card(r)
        for r in next_days
    )

    content = f"""

    <div style="
        padding:14px;
        background:#eff6ff;
        border-left:4px solid #2563eb;
        border-radius:8px;
        font-size:13px;
        line-height:1.7;
    ">
        <strong>DEIN BIG-WAVE-ÜBERBLICK</strong>
        <div style="margin-top:5px;">
            Modellbasierte Einschätzung für
            die kommenden Tage – mit Fokus
            auf spontane Ausflüge von Lissabon.
        </div>
    </div>

    {section_title("01 / Heute")}
    {today_html}

    {section_title("02 / Die 3 besten Modellfenster")}
    {best_html}

    {section_title("03 / 7-Tage-Ausblick")}
    {forecast_html}

    """

    html_body = email_layout(
        "Dein täglicher Swell- & Wetterbericht",
        content,
        now
    )

    text_body = (
        f"Nazaré Tagesbericht {now:%d.%m.%Y}\n\n"
        + "HEUTE\n"
        + "\n".join(map(describe, today))
        + "\n\nTOP 3\n"
        + "\n".join(map(describe, ranked))
        + "\n\nWEITERE TAGE\n"
        + "\n".join(map(describe, next_days))
        + DISCLAIMER
    )

    send(
        f"Nazaré Tagesbericht | {now:%d.%m.%Y}",
        text_body,
        html_body
    )

    print("Daily report sent successfully.")


# --------------------------------------------------
# ALERT REPORT
# --------------------------------------------------

def alert_report(days, now):

    upcoming = [
        r for r in days
        if now.date()
        <= r["t"].date()
        <= now.date() + dt.timedelta(days=3)
    ]

    candidates = [
        r for r in upcoming
        if r["score"] >= MIN_ALERT_SCORE
        and r["status"].startswith(("GRÜN", "GELB"))
    ]

    if STATE.exists():
        state = json.loads(STATE.read_text())
    else:
        state = {}

    to_send = []

    for r in candidates:

        is_today = r["t"].date() == now.date()

        phase = "today" if is_today else "advance"

        key = f'{r["t"]:%Y-%m-%d}:{phase}'

        if key not in state:
            to_send.append((key, r, is_today))

    if not to_send:
        print("No new qualifying alerts.")
        return

    cards = []
    lines = []

    for key, r, is_today in to_send:

        label = (
            "HEUTE PRÜFEN"
            if is_today
            else "BIG-WAVE-FRÜHWARNUNG"
        )

        heading = (
            "Heute: Bedingungen vor Ort prüfen"
            if is_today
            else "Mögliches Big-Wave-Fenster"
        )

        cards.append(
            section_title(heading)
            + day_card(r, featured=True)
        )

        lines.append(label + " | " + describe(r))

    content = f"""

    <div style="
        background:#fff3d6;
        border-left:4px solid #d69e2e;
        padding:17px;
        border-radius:9px;
        font-size:13px;
        line-height:1.7;
    ">
        <strong>BIG-WAVE-FRÜHINDIKATOR</strong>

        <div style="margin-top:7px;">
            Ein neues interessantes Modellfenster
            wurde erkannt. Das ist eine Vorwarnung
            und keine bestätigte Surf-Session.
            Bitte aktuelle Bedingungen prüfen,
            bevor ihr von Lissabon losfahrt.
        </div>
    </div>

    {''.join(cards)}

    """

    html_body = email_layout(
        "Neue potenzielle Big-Wave-Bedingungen",
        content,
        now
    )

    text_body = (
        f"NAZARÉ BIG WAVE ALERT\n"
        f"{now:%d.%m.%Y %H:%M}\n\n"
        + "\n".join(lines)
        + DISCLAIMER
    )

    send(
        "NAZARÉ BIG WAVE ALERT | Neues Modellfenster",
        text_body,
        html_body
    )

    for key, r, is_today in to_send:
        state[key] = now.isoformat()

    STATE.write_text(
        json.dumps(state, indent=2) + "\n"
    )

    print(f"Sent {len(to_send)} alerts.")


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    now = dt.datetime.now(TZ)

    if now.date() > UNTIL:
        print("Monitoring period completed.")
        return

    mode = os.getenv("MODE", "daily").lower()

    if mode not in ("daily", "alert"):
        raise ValueError(
            "MODE must be 'daily' or 'alert'"
        )

    items = records()

    days = best_by_day(items, now)

    if not days:
        raise RuntimeError(
            "No usable forecast data available."
        )

    if mode == "daily":
        daily_report(days, now)

    elif mode == "alert":
        alert_report(days, now)


if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        print(
            f"Radar error: {error}",
            file=sys.stderr
        )

        raise
