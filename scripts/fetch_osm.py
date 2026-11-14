"""Build osm.json for the TNP dashboard: cable cars and ski lifts, cycle routes and cycle paths.

Source: OpenStreetMap via the Overpass API (© OpenStreetMap contributors, ODbL).
Coordinates are projected to D96/TM (EPSG:3794) and shifted to the scene grid of week.json
(x east from the west edge, y south from the north edge, metres); heights come from dem.json.
These layers are static: there is no public data on when lifts run or how many cyclists ride.

Usage:  python fetch_osm.py [path/to/tnp-dashboard]
Only the Python standard library is used.
"""
import base64, json, math, sys, time, urllib.parse, urllib.request
from array import array
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "tnp-dashboard/1.0 (static map layers)", "Accept": "application/json"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]

# ---- D96/TM (GRS80, central meridian 15 E, k0 0.9999, false easting 500 km, false northing -5000 km) ----
A, F = 6378137.0, 1 / 298.257222101
E2 = F * (2 - F); EP2 = E2 / (1 - E2); K0, LON0, FE, FN = 0.9999, math.radians(15), 500000.0, -5000000.0
M1 = 1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256
M2 = 3 * E2 / 8 + 3 * E2**2 / 32 + 45 * E2**3 / 1024
M3 = 15 * E2**2 / 256 + 45 * E2**3 / 1024
M4 = 35 * E2**3 / 3072


def tm(lat, lon):
    p, l = math.radians(lat), math.radians(lon) - LON0
    n = A / math.sqrt(1 - E2 * math.sin(p) ** 2); t = math.tan(p) ** 2; c = EP2 * math.cos(p) ** 2; a = math.cos(p) * l
    m = A * (M1 * p - M2 * math.sin(2 * p) + M3 * math.sin(4 * p) - M4 * math.sin(6 * p))
    x = K0 * n * (a + (1 - t + c) * a**3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a**5 / 120)
    y = K0 * (m + n * math.tan(p) * (a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a**4 / 24 + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a**6 / 720))
    return FE + x, FN + y


def inv(e, n):
    """lat, lon for an easting/northing (Newton iteration on tm)."""
    lat, lon = 46.4, 13.9
    for _ in range(20):
        x0, y0 = tm(lat, lon); dx, dy = e - x0, n - y0
        if abs(dx) + abs(dy) < 1e-3: break
        xa, ya = tm(lat + 1e-5, lon); xo, yo = tm(lat, lon + 1e-5)
        j = [[(xa - x0) / 1e-5, (xo - x0) / 1e-5], [(ya - y0) / 1e-5, (yo - y0) / 1e-5]]
        det = j[0][0] * j[1][1] - j[0][1] * j[1][0]
        lat += (j[1][1] * dx - j[0][1] * dy) / det; lon += (-j[1][0] * dx + j[0][0] * dy) / det
    return lat, lon


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "tnp-dashboard"
    meta = json.loads((root / "week.json").read_text(encoding="utf-8"))["meta"]
    demj = json.loads((root / "dem.json").read_text(encoding="utf-8"))
    dem = array("H"); dem.frombytes(base64.b64decode(demj["b64"]))
    ox, oy, res, mw, mh = meta["origin"][0], meta["origin"][1], meta["res"], meta["mw"], meta["mh"]
    W, H = mw * res, mh * res
    step = res * mw / (mw - 1)          # the terrain mesh spreads mw vertices over the full width

    def z_at(x, y):
        c = min(mw - 1.001, max(0, x / step)); r = min(mh - 1.001, max(0, y / (res * mh / (mh - 1))))
        c0, r0 = int(c), int(r); fc, fr = c - c0, r - r0
        g = lambda rr, cc: dem[rr * mw + cc]
        return (g(r0, c0) * (1 - fc) + g(r0, c0 + 1) * fc) * (1 - fr) + (g(r0 + 1, c0) * (1 - fc) + g(r0 + 1, c0 + 1) * fc) * fr

    to_xy = lambda lat, lon: (lambda e, n: (e - ox, oy - n))(*tm(lat, lon))
    inside = lambda x, y: 0 <= x <= W and 0 <= y <= H
    corners = [inv(ox, oy), inv(ox + W, oy), inv(ox, oy - H), inv(ox + W, oy - H)]
    s, n = min(c[0] for c in corners), max(c[0] for c in corners)
    w, e = min(c[1] for c in corners), max(c[1] for c in corners)
    bbox = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"
    print("bbox", bbox)
    q = f"""[out:json][timeout:180];
(
  way["aerialway"~"^(cable_car|gondola|mixed_lift|chair_lift|drag_lift|t-bar|j-bar|platter|rope_tow)$"]({bbox});
  relation["route"~"^(bicycle|mtb)$"]({bbox});
  way["highway"="cycleway"]({bbox});
);
out body geom;"""
    for k in range(3):
        try:
            req = urllib.request.Request(OVERPASS[k], data=urllib.parse.urlencode({"data": q}).encode(), headers=UA)
            with urllib.request.urlopen(req, timeout=240) as r:
                els = json.loads(r.read().decode("utf-8"))["elements"]
            break
        except Exception as ex:
            if k == 2: raise
            print("  overpass retry:", ex); time.sleep(10 + 10 * k)
    print(len(els), "elements")

    def runs(geom):
        """Parts of a line inside the extent, densified every 60 m and thinned to 25 m."""
        out, cur = [], []
        pts = [to_xy(g["lat"], g["lon"]) for g in geom if g]
        for i, (x, y) in enumerate(pts):
            if i:
                px, py = pts[i - 1]; d = math.hypot(x - px, y - py); k = max(1, int(d // 60))
                seg = [(px + (x - px) * j / k, py + (y - py) * j / k) for j in range(1, k + 1)]
            else:
                seg = [(x, y)]
            for sx, sy in seg:
                if inside(sx, sy):
                    if not cur or math.hypot(sx - cur[-1][0], sy - cur[-1][1]) >= 25 or (sx, sy) == pts[-1]: cur.append((sx, sy))
                elif cur:
                    if len(cur) > 1: out.append(cur)
                    cur = []
        if len(cur) > 1: out.append(cur)
        return out

    KIND = {"cable_car": "cable", "gondola": "cable", "mixed_lift": "chair", "chair_lift": "chair"}
    lifts, cyc, seen = [], [], set()
    for el in els:
        tg = el.get("tags", {})
        if el["type"] == "way" and "aerialway" in tg:
            # lifts in service only: no disused, abandoned or ruined lifts, no freight or museum ropeways, no hand-pulled crossings
            if any(k in tg for k in ("disused", "abandoned", "ruins", "historic:aerialway", "disused:aerialway")) or tg.get("usage") == "freight" \
                    or "manually" in tg.get("note", ""): continue
            pts =[to_xy(g["lat"], g["lon"]) for g in el["geometry"]]
            if not all(inside(x, y) for x, y in pts): continue
            # cable height: 18 m above the ground at stations and pylons; add a support where the ground rises above the straight span
            line = [[round(x), round(y), round(z_at(x, y) + 18)] for x, y in pts]
            fixed = [line[0]]
            for a, b in zip(line, line[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1]); worst = None
                for j in range(1, max(2, int(L // 45))):
                    u = j / max(2, int(L // 45)); x = a[0] + (b[0] - a[0]) * u; y = a[1] + (b[1] - a[1]) * u
                    over = z_at(x, y) + 8 - (a[2] + (b[2] - a[2]) * u)
                    if over > 0 and (worst is None or over > worst[0]): worst = (over, x, y)
                if worst: fixed.append([round(worst[1]), round(worst[2]), round(z_at(worst[1], worst[2]) + 18)])
                fixed.append(b)
            lifts.append({"n": tg.get("name", ""), "k": KIND.get(tg["aerialway"], "drag"), "p": fixed})
        elif el["type"] == "relation":
            net = "mtb" if tg.get("route") == "mtb" else tg.get("network", "lcn")
            for m in el.get("members", []):
                if m.get("type") != "way" or not m.get("geometry") or ("r", m["ref"]) in seen: continue
                seen.add(("r", m["ref"]))
                for part in runs(m["geometry"]):
                    cyc.append({"n": tg.get("name", tg.get("ref", "")), "c": net, "p": [[round(x), round(y), round(z_at(x, y))] for x, y in part]})
        elif el["type"] == "way" and tg.get("highway") == "cycleway":
            if ("r", el["id"]) in seen: continue
            seen.add(("r", el["id"]))
            for part in runs(el["geometry"]):
                cyc.append({"n": tg.get("name", ""), "c": "path", "p": [[round(x), round(y), round(z_at(x, y))] for x, y in part]})
    O = {"src": "© OpenStreetMap contributors (ODbL), Overpass API", "built": time.strftime("%Y-%m-%d"), "lifts": lifts, "cycle": cyc}
    (root / "osm.json").write_text(json.dumps(O, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    km = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for c in cyc for a, b in zip(c["p"], c["p"][1:])) / 1000
    print(f"lifts {len(lifts)} ({sum(l['k']=='cable' for l in lifts)} cable cars or gondolas, {sum(l['k']=='chair' for l in lifts)} chair lifts), "
          f"cycle lines {len(cyc)} ({km:.0f} km), {(root / 'osm.json').stat().st_size // 1024} KB")
    for l in lifts:
        if l["k"] != "drag": print("  ", l["k"], l["n"])


if __name__ == "__main__":
    main()
