#!/usr/bin/env python3
"""
Daily HubSpot Leads Report
MQL/SQL by SEO/SEM — pacing vs monthly goals + WoW comparison
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from calendar import monthrange

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
BASE_URL = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

# Monthly goals 2026
GOALS_2026 = {
    6:  {"MQL_SEM": 685,  "SQL_SEM": 411, "MQL_SEO": 114, "SQL_SEO": 68},
    7:  {"MQL_SEM": 1080, "SQL_SEM": 648, "MQL_SEO": 124, "SQL_SEO": 74},
    8:  {"MQL_SEM": 1080, "SQL_SEM": 648, "MQL_SEO": 124, "SQL_SEO": 74},
    9:  {"MQL_SEM": 674,  "SQL_SEM": 405, "MQL_SEO": 114, "SQL_SEO": 68},
    10: {"MQL_SEM": 860,  "SQL_SEM": 516, "MQL_SEO": 107, "SQL_SEO": 64},
    11: {"MQL_SEM": 874,  "SQL_SEM": 524, "MQL_SEO": 124, "SQL_SEO": 74},
    12: {"MQL_SEM": 537,  "SQL_SEM": 322, "MQL_SEO": 114, "SQL_SEO": 68},
}

SEO_SOURCES = ["ORGANIC_SEARCH", "DIRECT_TRAFFIC", "OTHER_CAMPAIGNS"]
SEM_SOURCES = ["PAID_SEARCH", "PAID_SOCIAL"]
SOURCE_LABELS = {
    "ORGANIC_SEARCH": "Organic Search",
    "DIRECT_TRAFFIC": "Direct Traffic",
    "OTHER_CAMPAIGNS": "Other Campaigns",
    "PAID_SEARCH": "Paid Search",
    "PAID_SOCIAL": "Paid Social",
}

MQL_PROP = "hs_v2_date_entered_marketingqualifiedlead"
SQL_PROP = "hs_v2_date_entered_salesqualifiedlead"

MONTH_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo",
    6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre",
    10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def to_ms(dt: datetime) -> str:
    return str(int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000))


def count_leads(start_dt, end_dt, lifecycle_prop, source_digital, source_original=None):
    filters = [
        {"propertyName": lifecycle_prop, "operator": "GTE", "value": to_ms(start_dt)},
        {"propertyName": lifecycle_prop, "operator": "LTE", "value": to_ms(end_dt)},
        {"propertyName": "original_source_resumen_digital", "operator": "EQ", "value": source_digital},
    ]
    if source_original:
        filters.append({"propertyName": "hs_analytics_source", "operator": "EQ", "value": source_original})

    payload = {
        "filterGroups": [{"filters": filters}],
        "limit": 1,
        "properties": ["hs_analytics_source"],
    }

    try:
        r = requests.post(
            f"{BASE_URL}/crm/v3/objects/contacts/search",
            headers=HEADERS, json=payload, timeout=30,
        )
        if r.status_code == 200:
            return r.json().get("total", 0)
        print(f"[WARN] {source_digital}/{source_original}: HTTP {r.status_code}", file=sys.stderr)
    except requests.RequestException as e:
        print(f"[ERROR] {e}", file=sys.stderr)
    return 0


def fetch_snapshot(start_dt, end_dt):
    """Returns dict with keys like MQL_SEO, SQL_SEM — each a dict of source→count + total."""
    data = {}
    for lc_prop, lc_label in [(MQL_PROP, "MQL"), (SQL_PROP, "SQL")]:
        for dig_src, sources in [("SEO", SEO_SOURCES), ("SEM", SEM_SOURCES)]:
            key = f"{lc_label}_{dig_src}"
            data[key] = {src: count_leads(start_dt, end_dt, lc_prop, dig_src, src) for src in sources}
            data[key]["total"] = count_leads(start_dt, end_dt, lc_prop, dig_src)
    return data


def pacing_pct(actual, goal, day, total_days):
    expected = goal * (day / total_days)
    return (actual / expected * 100) if expected else 0


def pacing_icon(pct):
    if pct >= 110:
        return "🟢"
    elif pct >= 90:
        return "🟡"
    return "🔴"


def wow_str(curr, prev):
    diff = curr - prev
    sign = "+" if diff >= 0 else ""
    if prev > 0:
        return f"{sign}{diff} ({sign}{(diff/prev*100):.1f}%)"
    return f"{sign}{diff}"


def build_report(today: datetime, curr: dict, prev: dict, lw_label: str) -> str:
    month = today.month
    year = today.year
    day = today.day
    total_days = monthrange(year, month)[1]
    goals = GOALS_2026.get(month, {})

    lines = [
        f"📊 *REPORTE DIARIO DE LEADS — HubSpot*",
        f"📅 {today.strftime('%d/%m/%Y')}  |  Día {day}/{total_days} de {MONTH_ES[month]} {year}",
        "━" * 50,
    ]

    def block(title, mql_key, sql_key, sources, src_type):
        out = [f"\n{title}"]
        for label, key in [("MQL", mql_key), ("SQL", sql_key)]:
            goal = goals.get(key, 0)
            actual = curr[key]["total"]
            actual_lw = prev[key]["total"]
            p = pacing_pct(actual, goal, day, total_days)
            goal_pct = (actual / goal * 100) if goal else 0

            out.append(f"\n*{label} {src_type}*")
            for src in sources:
                out.append(f"  {SOURCE_LABELS[src]:<22} {curr[key].get(src, 0):>5}")
            out.append(f"  {'─'*30}")
            out.append(f"  {'TOTAL ' + src_type:<22} *{actual:>5}*   (meta: {goal})")
            out.append(f"  Avance meta: {goal_pct:.1f}%")
            out.append(f"  Pacing: {pacing_icon(p)} {p:.0f}% vs ritmo esperado ({goal * day // total_days} esperados hoy)")
            out.append(f"  WoW vs {lw_label}: {wow_str(actual, actual_lw)}")
        return out

    lines += block("🔍 *DASHBOARD SEO — Supply | B2C | SEO*",
                   "MQL_SEO", "SQL_SEO", SEO_SOURCES, "SEO")
    lines += block("\n📢 *DASHBOARD SEM — Combinado Search+Social*",
                   "MQL_SEM", "SQL_SEM", SEM_SOURCES, "SEM")

    lines += [
        "\n" + "━" * 50,
        "_Datos en tiempo real desde HubSpot CRM API_",
    ]
    return "\n".join(lines)


def main():
    # Chile time = UTC-4 (winter / junio-agosto)
    utc_now = datetime.now(timezone.utc)
    today = (utc_now + timedelta(hours=-4)).replace(tzinfo=None)
    last_week = today - timedelta(days=7)

    month_start = datetime(today.year, today.month, 1)
    today_end = today.replace(hour=23, minute=59, second=59, microsecond=0)

    # WoW: if same month, compare MTD same month; if crosses month, use prior month start
    if last_week.month == today.month:
        lw_start = month_start
    else:
        lw_start = datetime(last_week.year, last_week.month, 1)
    lw_end = last_week.replace(hour=23, minute=59, second=59, microsecond=0)

    print("Consultando HubSpot...", file=sys.stderr, flush=True)
    curr = fetch_snapshot(month_start, today_end)
    prev = fetch_snapshot(lw_start, lw_end)

    lw_label = last_week.strftime("%d/%m")
    report = build_report(today, curr, prev, lw_label)
    print(report)


if __name__ == "__main__":
    main()
