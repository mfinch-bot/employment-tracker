"""Baixa todas as series do BLS e grava data/raw.json."""
import json, os, sys, time, datetime as dt, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
FIRST_YEAR = 2009


def post(ids, start, end, key):
    body = json.dumps({"seriesid": ids, "startyear": str(start), "endyear": str(end),
                       "registrationkey": key}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json",
                                             "User-Agent": "employment-tracker"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.load(r)
            if out.get("status") == "REQUEST_SUCCEEDED":
                return out
            print("BLS:", out.get("status"), out.get("message"), file=sys.stderr)
        except Exception as e:  # rede instavel: tenta de novo
            print("erro de rede:", type(e).__name__, file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    raise SystemExit("BLS nao respondeu")


def fetch_all(key):
    ids = sorted({s["id"] for s in json.load(open(ROOT / "scripts/series.json")).values()})
    this_year = dt.datetime.utcnow().year
    raw = {}
    for i in range(0, len(ids), 50):
        out = post(ids[i:i + 50], FIRST_YEAR, this_year, key)
        for s in out["Results"]["series"]:
            pts = {}
            for p in s["data"]:
                if p["period"].startswith("M") and p["period"] != "M13":
                    try:
                        pts[f'{p["year"]}-{p["period"][1:]}'] = float(p["value"])
                    except ValueError:
                        pts[f'{p["year"]}-{p["period"][1:]}'] = None
            raw[s["seriesID"]] = dict(sorted(pts.items()))
    missing = [i for i in ids if not raw.get(i)]
    if missing:
        raise SystemExit(f"Series sem dados: {missing}")
    return raw


if __name__ == "__main__":
    raw = fetch_all(os.environ["BLS_API_KEY"])
    (ROOT / "data").mkdir(exist_ok=True)
    json.dump(raw, open(ROOT / "data/raw.json", "w"), separators=(",", ":"))
    print(len(raw), "series; ultimo mes", max(max(v) for v in raw.values()))
