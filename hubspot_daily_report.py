#!/usr/bin/env python3
"""
hubspot_daily_report.py — Daily HubSpot Leads Pacing Report (SEO & SEM · MQL / SQL)
Outputs a pre-formatted Slack message to stdout.
"""

import os, sys, requests, calendar
from datetime import datetime, timedelta, date
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN     = os.environ.get
TEAM_B2C  = "3499247"  # Captación B2C (987 contacts in June, largest in API)

GOALS = {
    "2026-06": {"MQL_SEM": 685,  "SQL_SEM": 411,  "MQL_SEO": 114, "SQL_SEO": 68},
    "2026-07": {"MQL_SEM": 1080, "SQL_SEM": 648,  "MQL_SEO": 124, "SQL_SEO": 74},
    "2026-08": {"MQL_SEM": 1080, "SQL_SEM": 648,  "MQL_SEO": 124, "SQL_SEO": 74},
    "2026-09": {"MQL_SEM": 674,  "SQL_SEM": 405,  "MQL_SEO": 114, "SQL_SEO": 68},
    "2026-10": {"MQL_SEM": 860,  "SQL_SEM": 516,  "MQL_SEO": 107, "SQL_SEO": 64},
    "2026-11": {"MQL_SEM": 874,  "SQL_SEM": 524,  "MQL_SEO": 124, "SQL_SEO": 74},
    "2026-12": {"MQL_SEM": 537,  "SQL_SEM": 322,  "MQL_SEO": 114, "SQL_SEO": 68},
}

SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"
FETCH_PROPS = ["createdate", "hs_analytics_source"]

SRC_LABELS = {
    "PAID_SEARCH":     "Paid Search",
    "PAID_SOCIAL":     "Paid Social",
    "ORGANIC_SEARCH":  "Organic Search",
    "DIRECT_TRAFFIC":  "Direct Traffic",
    "OTHER_CAMPAIGNS": "Other Campaigns",
    "EMAIL_MARKETING": "Email Marketing",
}

# ── HubSpot helpers ───────────────────────────────────────────────────────────
def _headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def _ms(d: date, eod=False) -> str:
    dt = datetime(d.year, d.month, d.day, 23 if eod else 0, 59 if eod else 0, 59 if eod else 0)
    return str(int(dt.timestamp() * 1000))

def fetch_all(filter_groups: list) -> list:
    """Paginate through all matching contacts; return list of property dicts."""
    results, after = [], None
    while True:
        body = {"filterGroups": filter_groups, "properties": FETCH_PROPS, "limit": 100}
        if after:
            body["after"] = after
        r = requests.post(SEARCH_URL, headers=_headers(), json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        results.extend(c["properties"] for c in data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return results

# ── Filter atoms ──────────────────────────────────────────────────────────────
def fg(filters: list) -> dict:
    return {"filters": filters}

def date_f(start: date) -> list:
    return [{"propertyName": "createdate", "operator": "GTE", "value": _ms(start)}]

SEM    = [{"propertyName": "hs_analytics_source", "operator": "IN",
           "values": ["PAID_SEARCH", "PAID_SOCIAL"]}]
SEO    = [{"propertyName": "hs_analytics_source", "operator": "NOT_IN",
           "values": ["OFFLINE", "PAID_SEARCH", "PAID_SOCIAL", "REFERRALS"]}]
SQL_ST = [{"propertyName": "hs_lead_status", "operator": "IN",
           "values": ["Calificado por ventas", "Cliente"]}]
TEAM_F = [{"propertyName": "hs_all_team_ids", "operator": "EQ", "value": TEAM_B2C}]
# Exclude contacts in "Descartado" lifecycle (internal ID 91549611) from MQL counts
NO_DESC = [{"propertyName": "lifecyclestage", "operator": "NEQ", "value": "91549611"}]

# ── Query builders ────────────────────────────────────────────────────────────
def q_sem_mql(start):
    return [fg(date_f(start) + SEM + TEAM_F)]

def q_sem_sql(start):
    return [fg(date_f(start) + SEM + SQL_ST + TEAM_F)]

def q_seo_mql(start):
    return [fg(date_f(start) + SEO + TEAM_F + NO_DESC)]

def q_seo_sql(start):
    # "Has ever been" in opportunity/SQL/customer: OR across filter groups
    # hs_v2_date_entered_* is set the first time a contact enters that stage
    base = date_f(start) + SEO + SQL_ST + TEAM_F
    return [
        fg(base + [{"propertyName": "hs_v2_date_entered_opportunity",        "operator": "HAS_PROPERTY"}]),
        fg(base + [{"propertyName": "hs_v2_date_entered_salesqualifiedlead", "operator": "HAS_PROPERTY"}]),
        fg(base + [{"propertyName": "hs_v2_date_entered_customer",           "operator": "HAS_PROPERTY"}]),
    ]

# ── Analysis ──────────────────────────────────────────────────────────────────
def daily_map(contacts: list) -> dict:
    counts = defaultdict(int)
    for c in contacts:
        cd = c.get("createdate", "")
        if cd:
            counts[cd[:10]] += 1
    return dict(counts)

def src_map(contacts: list) -> dict:
    counts = defaultdict(int)
    for c in contacts:
        counts[c.get("hs_analytics_source") or "UNKNOWN"] += 1
    return dict(counts)

def period_avg(dm: dict, start_d: date, end_d: date) -> float:
    n = (end_d - start_d).days + 1
    total = sum(dm.get((start_d + timedelta(days=i)).strftime("%Y-%m-%d"), 0) for i in range(n))
    return round(total / max(n, 1), 1)

def analyze(contacts: list, today: date, month_start: date, days_in_month: int) -> dict:
    total      = len(contacts)
    dm         = daily_map(contacts)
    days_so_far = (today - month_start).days + 1

    rate  = total / days_so_far if days_so_far > 0 else 0
    proj  = round(rate * days_in_month)

    # Rhythm: first N-5 days vs last 5 days
    early_end = today - timedelta(days=5)
    if early_end < month_start:
        early_end = month_start
    avg_early  = period_avg(dm, month_start, early_end)
    avg_recent = period_avg(dm, early_end + timedelta(days=1), today)

    # WoW: accumulated total as of 7 days ago
    wow_day   = today - timedelta(days=7)
    wow_total = sum(v for d, v in dm.items() if d <= wow_day.strftime("%Y-%m-%d"))

    return {
        "total":      total,
        "days":       days_so_far,
        "rate":       round(rate, 1),
        "proj":       proj,
        "avg_early":  avg_early,
        "avg_recent": avg_recent,
        "wow_total":  wow_total,
        "sources":    src_map(contacts),
    }

# ── Formatting helpers ────────────────────────────────────────────────────────
def pct(n, d):   return f"{round(n/d*100)}%" if d else "n/a"
def sgn(x):      return "+" if x >= 0 else ""

def gap_str(gap, goal):
    gp   = round(gap / goal * 100) if goal else 0
    icon = "✅" if gap >= 0 else "🚨"
    return f"{icon} {sgn(gap)}{gap} ({sgn(gp)}{gp}%)"

def rhythm_icon(d):
    if d > 5:   return "🚀"
    if d > -10: return "🔸"
    return "🚨"

def wow_icon(d): return "🟢" if d >= 0 else "🔴"

def src_line(key, mql_src, sql_src):
    label = SRC_LABELS.get(key, key)
    return f"  {label} → MQL: {mql_src.get(key, 0)} · SQL: {sql_src.get(key, 0)}"

# ── Report builder ────────────────────────────────────────────────────────────
def build_report(metrics: dict, today: date, month_start: date, days_in_month: int) -> str:
    G         = GOALS.get(today.strftime("%Y-%m"), {})
    day       = (today - month_start).days + 1
    days_left = days_in_month - day

    sm = metrics["MQL_SEM"]
    ss = metrics["SQL_SEM"]
    em = metrics["MQL_SEO"]
    es = metrics["SQL_SEO"]

    # ── REAL VS META ──────────────────────────────────────────────────────────
    def meta_row(lbl, m, gk):
        r, g = m["total"], G.get(gk, 0)
        return (f"  {lbl:<10} {r:>5}  {g:>5}  {pct(r,g):>7}  "
                f"~{m['proj']:<5}  {gap_str(m['proj']-g, g)}")

    meta_tbl = "\n".join([
        f"  {'Canal':<10} {'Real':>5}  {'Meta':>5}  {'%Avance':>7}  {'Proy.':>6}  Gap",
        "  " + "─" * 58,
        meta_row("MQL SEM", sm, "MQL_SEM"),
        meta_row("SQL SEM", ss, "SQL_SEM"),
        meta_row("MQL SEO", em, "MQL_SEO"),
        meta_row("SQL SEO", es, "SQL_SEO"),
    ])

    # ── DESGLOSE ─────────────────────────────────────────────────────────────
    sem_break = "\n".join(
        src_line(k, sm["sources"], ss["sources"])
        for k in ["PAID_SEARCH", "PAID_SOCIAL"]
    )
    seo_keys  = ["ORGANIC_SEARCH", "DIRECT_TRAFFIC", "OTHER_CAMPAIGNS", "EMAIL_MARKETING"]
    seo_lines = [src_line(k, em["sources"], es["sources"])
                 for k in seo_keys
                 if em["sources"].get(k, 0) + es["sources"].get(k, 0) > 0]
    seo_break = "\n".join(seo_lines) if seo_lines else "  (sin datos)"

    # ── RITMO ────────────────────────────────────────────────────────────────
    early_days = max(day - 5, 1)

    def rhythm_row(lbl, m):
        e, r = m["avg_early"], m["avg_recent"]
        delta = round((r - e) / e * 100) if e else 0
        return (f"  {lbl:<10} {e:>8.1f}/día  {r:>8.1f}/día  "
                f"{rhythm_icon(delta)} {sgn(delta)}{delta}%")

    rhythm_tbl = "\n".join([
        f"  {'Canal':<10} {'Prom.d1-'+str(early_days):>12}  {'Prom.últimos5':>13}  Δ Ritmo",
        "  " + "─" * 55,
        rhythm_row("MQL SEM", sm),
        rhythm_row("SQL SEM", ss),
        rhythm_row("MQL SEO", em),
        rhythm_row("SQL SEO", es),
    ])

    # ── WoW ──────────────────────────────────────────────────────────────────
    wow_ref = (today - timedelta(days=7)).strftime("%d/%m")

    def wow_row(lbl, m):
        curr, prev = m["total"], m["wow_total"]
        diff = curr - prev
        dp   = round(diff / prev * 100) if prev else 0
        return (f"  {lbl:<10} {prev:>10}  {curr:>10}  "
                f"{wow_icon(diff)} {sgn(diff)}{diff} ({sgn(dp)}{dp}%)")

    wow_tbl = "\n".join([
        f"  {'Canal':<10} {wow_ref+' acum.':>10}  {'Hoy acum.':>10}  Δ WoW",
        "  " + "─" * 50,
        wow_row("MQL SEM", sm),
        wow_row("SQL SEM", ss),
        wow_row("MQL SEO", em),
        wow_row("SQL SEO", es),
    ])

    # ── ALERTAS ───────────────────────────────────────────────────────────────
    alert_lines = []
    for lbl, m, gk in [("MQL SEM", sm, "MQL_SEM"), ("SQL SEM", ss, "SQL_SEM"),
                        ("MQL SEO", em, "MQL_SEO"), ("SQL SEO", es, "SQL_SEO")]:
        goal = G.get(gk, 0)
        if not goal:
            continue
        proj    = m["proj"]
        gap     = proj - goal
        recent  = m["avg_recent"]
        early   = m["avg_early"]
        rdelta  = round((recent - early) / early * 100) if early else 0
        needed  = round((goal - m["total"]) / days_left) if days_left > 0 else "∞"

        if gap < -0.15 * goal:
            alert_lines.append(
                f":rotating_light: *{lbl}* — riesgo alto: Proyecta {proj} vs meta {goal}. "
                f"Necesitan ~{needed}/día en {days_left} días restantes (ritmo actual: {recent}/día)."
            )
        elif gap < 0:
            alert_lines.append(
                f":large_yellow_circle: *{lbl}* — atención: Proyecta {proj} vs meta {goal}. "
                f"Ritmo reciente: {recent}/día."
            )
        elif rdelta < -30:
            alert_lines.append(
                f":rotating_light: *{lbl}* — caída de ritmo {rdelta}%: "
                f"De {early}/día → {recent}/día (últimos 5 días). Revisar fuentes."
            )
        else:
            alert_lines.append(
                f":white_check_mark: *{lbl}* — en camino: Proyecta {proj} vs meta {goal}."
            )

    alerts = "\n".join(alert_lines) if alert_lines else "Sin alertas críticas."

    MONTHS_ES = {
        1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
        7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"
    }
    month_name = f"{MONTHS_ES[today.month]} {today.year}"

    return f"""📊 *REPORTE DIARIO DE LEADS — {today.strftime('%d %b %Y').upper()}*
_Día {day} de {days_in_month} | {month_name} | Comparativa WoW vs {wow_ref}_

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*REAL VS META*
```
{meta_tbl}
```
_Proyección = ritmo actual extrapolado a fin de mes_

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*DESGLOSE SEM (mes actual)*
{sem_break}

*DESGLOSE SEO (mes actual)*
{seo_break}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*ANÁLISIS DE RITMO — días 1–{early_days} vs últimos 5 días*
```
{rhythm_tbl}
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*WoW — Acumulado hoy vs mismo día semana anterior ({wow_ref})*
```
{wow_tbl}
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*ALERTAS*
{alerts}"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    today         = date.today()
    month_start   = date(today.year, today.month, 1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    print(f"▶ {today} · día {(today-month_start).days+1}/{days_in_month}", file=sys.stderr)

    queries = {
        "MQL_SEM": (q_sem_mql, "MQL SEM"),
        "SQL_SEM": (q_sem_sql, "SQL SEM"),
        "MQL_SEO": (q_seo_mql, "MQL SEO"),
        "SQL_SEO": (q_seo_sql, "SQL SEO"),
    }

    metrics = {}
    for key, (qfn, label) in queries.items():
        print(f"  Fetching {label}...", file=sys.stderr)
        contacts      = fetch_all(qfn(month_start))
        metrics[key]  = analyze(contacts, today, month_start, days_in_month)
        print(f"  → {metrics[key]['total']} contactos", file=sys.stderr)

    report = build_report(metrics, today, month_start, days_in_month)
    print(report)
    return report


if __name__ == "__main__":
    main()
