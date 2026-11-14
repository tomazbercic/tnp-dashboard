"""Build / extend archive.json for the TNP dashboard.

Sources (public pages, no login):
  - JZ TNP visitor counters: per-counter detail page, last 60 days of daily totals
  - ARSO automatic weather stations: webmet archive, 10-min temperature and wind + 30-min precipitation -> hourly (CET)
  - ARSO river gauges: 30-day hourly tables (discharge, m3/s)

Each run fetches what the sources still offer and merges it into the existing archive, so
the archive keeps growing as long as the script runs at least every ~30 days (hydro window).

Usage:  python fetch_data.py [path/to/archive.json] [--days 60]
Only the Python standard library is used.
"""
import json, math, re, sys, time, urllib.request, datetime as dt
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "Mozilla/5.0 (tnp-dashboard data refresh)"}
TNP = "https://www.tnp.si"
TNP_LIST = TNP + "/sl/obisk-parka/aktualno/spremljanje-obiska/"

COUNTERS = [7, 61, 37, 27, 8, 46, 4, 55, 66, 60, 57, 65]          # ids used by the dashboard
METEO = {  # dashboard id -> ARSO webmet archive station id
    "KREDA-ICA": 1820, "KANIN": 2641, "VRSIC": 2846, "VOGEL": 2617, "RUDNO-POL": 1858,
    "PREDEL": 2700, "KRN": 2646, "ZGORN-RAD": 2621, "BOHIN-CES": 2614,
}
HYDRO = ["3014", "3180", "3200", "3260", "3300", "3320", "8031", "8060", "8080", "8332"]
EPOCH_1800 = dt.datetime(1800, 1, 1)


def get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # network hiccup: retry with backoff
            if k == tries - 1:
                raise
            time.sleep(2 + 3 * k)


def counters(start, end):
    """{id: {date: value}} from each counter's detail page (r=60d)."""
    page = get(TNP_LIST)
    links = dict(re.findall(r'/sl/obisk-parka/aktualno/spremljanje-obiska/podrobnosti/(\d+)/([^"\']+?\.html)', page))
    out = {}
    for cid in COUNTERS:
        slug = links.get(str(cid))
        if not slug:
            print(f"  counter {cid}: no detail link"); continue
        s = get(f"{TNP_LIST}podrobnosti/{cid}/{slug}?r=60d")
        m = re.search(r"labels\s*[=:]\s*\[([^\]]*)\]", s); d = re.search(r"data:\s*\[([^\]]*)\]", s)
        if not (m and d):
            print(f"  counter {cid}: no chart data"); continue
        labels = [x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()]
        vals = [x.strip() for x in d.group(1).split(",")]
        row = {}
        for lab, v in zip(labels, vals):
            day = dt.datetime.strptime(lab, "%d.%m.%Y").date()
            if start <= day <= end and v not in ("", "null"):
                row[day.isoformat()] = int(float(v))
        out[str(cid)] = row
        print(f"  counter {cid}: {len(row)} days")
        time.sleep(0.4)
    return out


def wind_hour(samples):
    """10-min (speed, direction) pairs -> (mean speed m/s, vector-mean direction the wind blows from, degrees)."""
    u = sum(f * math.sin(math.radians(d)) for f, d in samples); v = sum(f * math.cos(math.radians(d)) for f, d in samples)
    ff = sum(f for f, _ in samples) / len(samples)
    dd = round(math.degrees(math.atan2(u, v)) % 360) if (u or v) else None
    return round(ff, 1), dd


def archive_rows(aid, d1, d2, vars_):
    s = get(f"https://meteo.arso.gov.si/webmet/archive/data.xml?lang=si&vars={vars_}&group=halfhourlyData0"
            f"&type=halfhourly&id={aid}&d1={d1.isoformat()}&d2={d2.isoformat()}")
    for key, body in re.findall(r"_(\d{6,}):\{([^}]*)\}", s):
        when = EPOCH_1800 + dt.timedelta(minutes=int(key))
        a = re.search(r'p0:"(-?[\d.]+)"', body); b = re.search(r'p1:"(-?[\d.]+)"', body)
        yield when.strftime("%Y-%m-%dT%H"), (float(a.group(1)) if a else None), (float(b.group(1)) if b else None)


def meteo(start, end):
    """{id: {"t": {hour: mean}, "rr": {hour: sum}, "ff": {hour: mean speed}, "dd": {hour: direction}}}, hours in CET as served by the archive.
    The archive serves at most two variables per request: temperature and precipitation, then wind speed and direction."""
    out = {}
    for mid, aid in METEO.items():
        acc_t, acc_r, acc_w = {}, {}, {}
        d1 = start
        while d1 <= end:
            d2 = min(end, d1 + dt.timedelta(days=9))
            for hk, t, r in archive_rows(aid, d1, d2, "15,26"):
                if t is not None: acc_t.setdefault(hk, []).append(t)
                if r is not None: acc_r[hk] = acc_r.get(hk, 0.0) + r
            time.sleep(0.3)
            for hk, f, d in archive_rows(aid, d1, d2, "21,23"):
                if f is not None and d is not None: acc_w.setdefault(hk, []).append((f, d))
            d1 = d2 + dt.timedelta(days=1)
            time.sleep(0.3)
        # the archive lags about a day: fill its last hours from the 48-hour station feed.
        # Feed record (validEnd UTC + 1 h) = archive key (CET); 10-min precipitation goes to the
        # archive's 30-min slot ending at or after it, so hourly sums match the archive exactly.
        rt, rr, rn, rw = {}, {}, {}, {}
        try:
            h = get(f"https://meteo.arso.gov.si/uploads/probase/www/observ/surface/text/sl/recent/observationAms_{mid}_history.xml")
            for b in re.findall(r"<metData>(.*?)</metData>", h, re.S):
                ve = re.search(r"<validEnd>([^<]+)</validEnd>", b)
                if not ve: continue
                k = dt.datetime.strptime(ve.group(1), "%d.%m.%Y %H:%M UTC") + dt.timedelta(hours=1)
                t = re.search(r"<tavg>(-?[\d.]+)</tavg>", b); p = re.search(r"<rr_val>(-?[\d.]+)</rr_val>", b)
                if t: rt.setdefault(k.strftime("%Y-%m-%dT%H"), []).append(float(t.group(1)))
                f = re.search(r"<ffavg_val>(-?[\d.]+)</ffavg_val>", b) or re.search(r"<ff_val>(-?[\d.]+)</ff_val>", b)
                d = re.search(r"<ddavg_val>(-?[\d.]+)</ddavg_val>", b) or re.search(r"<dd_val>(-?[\d.]+)</dd_val>", b)
                if f and d: rw.setdefault(k.strftime("%Y-%m-%dT%H"), []).append((float(f.group(1)), float(d.group(1))))
                if p:
                    slot = k + dt.timedelta(minutes=(-k.minute) % 30)
                    hk = slot.strftime("%Y-%m-%dT%H")
                    rr[hk] = rr.get(hk, 0.0) + float(p.group(1)); rn[hk] = rn.get(hk, 0) + 1
        except Exception as e:
            print(f"  meteo {mid}: recent feed failed ({e})")
        last = (end + dt.timedelta(days=1)).isoformat()
        filled = 0
        for hk, v in rt.items():
            if hk[:10] < last and len(v) == 6 and len(acc_t.get(hk, [])) < 6:
                acc_t[hk] = v; filled += 1
                if rn.get(hk) == 6: acc_r[hk] = rr[hk]
        for hk, v in rw.items():
            if hk[:10] < last and len(v) == 6 and len(acc_w.get(hk, [])) < 6: acc_w[hk] = v
        wind = {k: wind_hour(v) for k, v in acc_w.items() if k[:10] <= end.isoformat()}
        out[mid] = {"t": {k: round(sum(v) / len(v), 1) for k, v in acc_t.items() if k[:10] <= end.isoformat()},
                    "rr": {k: round(v, 1) for k, v in acc_r.items() if k[:10] <= end.isoformat()},
                    "ff": {k: w[0] for k, w in wind.items()}, "dd": {k: w[1] for k, w in wind.items() if w[1] is not None}}
        print(f"  meteo {mid}: {len(out[mid]['t'])} h temperature, {len(out[mid]['rr'])} h precipitation, {len(out[mid]['ff'])} h wind ({filled} h from the 48-hour feed)")
    return out


def hydro():
    """{id: {hour_iso: discharge}} from the 30-day hourly tables."""
    out = {}
    for hid in HYDRO:
        s = get(f"https://www.arso.gov.si/vode/podatki/amp/H{hid}_t_30.html")
        row = {}
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S):
            cells = [re.sub("<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) >= 3 and re.match(r"\d{1,2}\.\d{1,2}\.\d{4} \d{1,2}:\d{2}$", cells[0]):
                try:
                    when = dt.datetime.strptime(cells[0], "%d.%m.%Y %H:%M")
                    row[when.strftime("%Y-%m-%dT%H")] = float(cells[2].replace(",", "."))
                except ValueError:
                    pass  # '-' or empty: missing value
        out[hid] = row
        print(f"  hydro {hid}: {len(row)} h")
        time.sleep(0.3)
    return out


def load_old(path):
    """Existing archive as keyed dicts, so a merge never loses older data."""
    if not path.exists():
        return {"counters": {}, "meteo": {}, "hydro": {}}
    A = json.loads(path.read_text(encoding="utf-8"))
    d0 = dt.date.fromisoformat(A["start"]); h0 = dt.datetime.fromisoformat(A["start"] + "T00:00")
    day = lambda i: (d0 + dt.timedelta(days=i)).isoformat()
    hour = lambda i: (h0 + dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H")
    keyed = lambda arr, f: {f(i): v for i, v in enumerate(arr) if v is not None}
    return {"start": d0,
            "counters": {k: keyed(v, day) for k, v in A["counters"].items()},
            "meteo": {k: {n: keyed(v.get(n, []), hour) for n in ("t", "rr", "ff", "dd")} for k, v in A["meteo"].items()},
            "hydro": {k: keyed(v, hour) for k, v in A["hydro"].items()}}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 60
    path = Path(args[0]) if args else Path(__file__).resolve().parent.parent / "tnp-dashboard" / "archive.json"
    today = dt.date.today()
    end = today - dt.timedelta(days=1)                       # last complete day
    start = end - dt.timedelta(days=days - 1)
    old = load_old(path)
    print(f"fetching {start} .. {end}")
    print("counters"); C = counters(start, end)
    # TNP may not have published yesterday yet (the chart then shows 0 everywhere): stop at the last day with passages
    tot = lambda d: sum(row.get(d.isoformat(), 0) for row in C.values())
    while end > start and tot(end) == 0 and tot(end - dt.timedelta(days=1)) > 0:
        print(f"  no passages yet for {end}, archive ends a day earlier")
        for row in C.values(): row.pop(end.isoformat(), None)
        end -= dt.timedelta(days=1)
    print("meteo"); M = meteo(start, end)
    print("hydro"); H = hydro()

    a0 = min(start, old.get("start", start))
    nd = (end - a0).days + 1
    hours = [(dt.datetime.combine(a0, dt.time()) + dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H") for i in range(nd * 24)]
    dates = [(a0 + dt.timedelta(days=i)).isoformat() for i in range(nd)]
    merge = lambda new, prev, keys: [new.get(k, prev.get(k)) for k in keys]
    A = {
        "start": a0.isoformat(), "end": end.isoformat(),
        "built": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": "counters: daily totals (JZ TNP); meteo: hourly mean temperature, precipitation sum, mean wind speed m/s and vector-mean direction the wind blows from (ARSO, CET); hydro: hourly discharge m3/s (ARSO)",
        "counters": {str(c): merge(C.get(str(c), {}), old["counters"].get(str(c), {}), dates) for c in COUNTERS},
        "meteo": {m: {n: merge(M.get(m, {}).get(n, {}), old["meteo"].get(m, {}).get(n, {}), hours) for n in ("t", "rr", "ff", "dd")} for m in METEO},
        "hydro": {h: merge(H.get(h, {}), old["hydro"].get(h, {}), hours) for h in HYDRO},
    }
    path.write_text(json.dumps(A, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {path} ({path.stat().st_size // 1024} KB), {a0} .. {end}, {nd} days")


if __name__ == "__main__":
    main()
