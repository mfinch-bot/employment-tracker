"""Pagina do ADP: mesmas contas da aba Graficos M do ADP.xlsx, com o historico publicado pela ADP.

Modos:
  --watch  no dia do release, consulta o arquivo da ADP a cada 10s a partir de 8:14:30 ET
  --once   baixa uma vez e publica se houver novidade
"""
import csv, datetime as dt, io, json, os, pathlib, sys, time, urllib.request, zipfile
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build_dashboard as bd, calc

ROOT = pathlib.Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
BRT = ZoneInfo("America/Sao_Paulo")
BASE = "https://adpemploymentreport.com"
SECTORS = ["Natural resources and mining", "Construction", "Manufacturing", "Trade, transportation, and utilities",
           "Information", "Financial activities", "Professional and business services",
           "Education and health services", "Leisure and hospitality", "Other services"]
OFFICIAL = dt.time(8, 15)
START = dt.time(8, 14, 30)
STOP = dt.time(9, 30)
POLL_SECONDS = 10


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 employment-tracker", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_zip(blob):
    """Le o historico mensal do zip. Devolve {categoria: {mes: (NSA, SA)}}."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        text = z.read(name).decode("utf-8-sig")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row["timestep"] != "M" or row["agg_RIS"] not in ("National", "Industry"):
            continue
        out.setdefault(row["category"], {})[row["date"][:7]] = (float(row["NER"]), float(row["NER_SA"]))
    return out


def try_download(day):
    """Tenta o arquivo do dia. O site responde 200 com HTML quando o arquivo ainda nao existe."""
    url = f"{BASE}/artifacts/us_ner/{day:%Y%m%d}/ADP_NER_history.zip?t={int(time.time())}"
    try:
        blob = get(url)
    except Exception as e:
        print("sem resposta:", type(e).__name__)
        return None
    return blob if blob[:2] == b"PK" else None


def latest_zip():
    info = json.loads(get(f"{BASE}/ner_production.json?t={int(time.time())}"))
    return get(info["reportDownloadLink"]), info


def next_dates(info):
    out = []
    for r in info.get("futureReports", []):
        try:
            out.append(dt.datetime.strptime(r["reportDate"], "%B %d, %Y").date().isoformat())
        except (KeyError, ValueError):
            pass
    return sorted(out)


def build_grid(D, as_of):
    G = {}
    def setc(c, r, x):
        G.setdefault(c, {})[r] = x
    sa_cols = dict(zip(["D", "E", "F", "H", "I", "J", "K", "L", "M", "N"], SECTORS))
    nsa_cols = dict(zip(["T", "U", "V", "X", "Y", "Z", "AA", "AB", "AC", "AD"], SECTORS))
    def diff(cat, m, i):
        a, b = D[cat].get(m), D[cat].get(calc.shift(m, -1))
        return None if a is None or b is None else (a[i] - b[i]) / 1000
    for r in range(4, 184):
        m = calc.shift(as_of, 4 - r)
        setc("A", r, m)
        for c, cat in sa_cols.items():
            setc(c, r, diff(cat, m, 1))
        for c, cat in nsa_cols.items():
            setc(c, r, diff(cat, m, 0))
        s = lambda cols: None if any(G[c].get(r) is None for c in cols) else sum(G[c][r] for c in cols)
        setc("C", r, s("DEF"))
        setc("G", r, s("HIJKLMN"))
        setc("B", r, None if G["C"][r] is None or G["G"][r] is None else G["C"][r] + G["G"][r])
        setc("S", r, s("TUV"))
        setc("W", r, s(["X", "Y", "Z", "AA", "AB", "AC", "AD"]))
        setc("R", r, diff("U.S.", m, 0))
    for r in range(4, 182):
        v = [G["B"].get(r + i) for i in range(3)]
        setc("O", r, None if None in v else sum(v) / 3)
    return G


def seasonal(G, as_of, col):
    y1 = int(as_of[:4])
    row = {G["A"][r]: r for r in G["A"]}
    out = {"y1": [], "y0": [], "p20": [], "med": [], "p80": []}
    for mm in range(1, 13):
        out["y1"].append(G[col].get(row.get(f"{y1}-{mm:02d}")))
        out["y0"].append(G[col].get(row.get(f"{y1 - 1}-{mm:02d}")))
        vals = [G[col][r] for r in range(4, 184)
                if int(G["A"][r][5:]) == mm and 2012 <= int(G["A"][r][:4]) <= 2019 and G[col][r] is not None]
        for k, p in (("p20", .2), ("med", .5), ("p80", .8)):
            out[k].append(calc.percentile(vals, p))
    return out


def bars(name, data, color, show=True, fmt="0"):
    return {"name": name, "type": "bar", "data": data, "color": color, "fill": color, "dash": None, "width": None,
            "noline": True, "marker": None, "markerColor": None, "show": show, "labels": [], "fmt": fmt, "yAxis": 0}


def line(name, data, color, dash=None, marker=False, labels=None, width=2.25):
    return {"name": name, "type": "line", "data": data, "color": color, "fill": None, "dash": dash, "width": width,
            "noline": False, "marker": ["circle", 5] if marker else ["none", None], "markerColor": None, "show": False,
            "labels": labels or [], "fmt": "0", "yAxis": 0}


def charts(D, G, as_of):
    M = calc.MONTHS
    y1 = int(as_of[:4])
    months = [G["A"][r] for r in range(123, 3, -1)]
    total = [G["B"][r] for r in range(123, 3, -1)]
    ma = [G["O"][r] for r in range(123, 3, -1)]
    n = len(months)
    bar1 = bars("ADP Increase", total, "A6A6A6", show=False)
    bar1["labels"] = [{"i": n - 13, "fmt": None, "fill": None}, {"i": n - 2, "fmt": None, "fill": None},
                      {"i": n - 1, "fmt": None, "fill": "FFFF00"}]
    out = [{"row": 5, "col": 1, "title": ["ADP"], "cats": [bd.month_label(m) for m in months], "date": True, "horizontal": False,
            "series": [bar1, line("3MMA", ma, "153D64", labels=[{"i": n - 1, "fmt": None, "fill": None}])],
            "axes": [{"min": -200, "max": 1000, "fmt": "General"}]}]
    sa, nsa = seasonal(G, as_of, "B"), seasonal(G, as_of, "R")
    out.append({"row": 27, "col": 1, "title": ["ADP SA"], "cats": M, "date": False, "horizontal": False,
                "series": [bars(str(y1 - 1), sa["y0"], "A6CAEC"), bars(str(y1), sa["y1"], "156082")],
                "axes": [{"min": None, "max": None, "fmt": "0"}]})
    out.append({"row": 45, "col": 1, "title": ["ADP NSA"], "cats": M, "date": False, "horizontal": False,
                "series": [bars(str(y1 - 1), nsa["y0"], "A6CAEC"), bars(str(y1), nsa["y1"], "156082")],
                "axes": [{"min": None, "max": None, "fmt": "0"}]})
    mm = as_of[5:]
    years = list(range(y1 - 14, y1 + 1))
    us = D["U.S."]
    by_year = [(us[f"{y}-{mm}"][0] - us[calc.shift(f"{y}-{mm}", -1)][0]) / 1000 for y in years]
    out.append({"row": 75, "col": 3, "title": [f"ADP Payroll Increase NSA - {M[int(mm) - 1]}"], "cats": years, "date": False,
                "horizontal": False, "series": [bars(None, by_year, "156082")], "axes": [{"min": None, "max": None, "fmt": "General"}]})
    order = [("Total", "B"), ("Goods-producing", "C"), ("Natural resources and mining", "D"), ("Construction", "E"),
             ("Manufacturing", "F"), ("Service-providing", "G"), ("Trade, transportation, and utilities", "H"),
             ("Information", "I"), ("Financial activities", "J"), ("Professional and business services", "K"),
             ("Education and health services", "L"), ("Leisure and hospitality", "M"), ("Other services", "N")]
    out.append({"row": 92, "col": 3, "title": ["ADP Breakdown by Sector"], "cats": [a for a, _ in order], "date": False, "horizontal": True,
                "series": [bars(M[int(mm) - 1], [G[c][4] for _, c in order], "156082"),
                           bars("Prior month", [G[c][5] for _, c in order], "A6CAEC")],
                "axes": [{"min": None, "max": None, "fmt": "General"}]})
    def block(title, col, row, pos):
        s = seasonal(G, as_of, col)
        return {"row": row, "col": pos, "title": [title], "cats": M, "date": False, "horizontal": False,
                "series": [line("p20", s["p20"], "0D0D0D", "sysDot"), line("med", s["med"], "000000"),
                           line("p80", s["p80"], "0D0D0D", "sysDot"), line(str(y1 - 1), s["y0"], "215F9A", marker=True),
                           line(str(y1), s["y1"], "C00000", marker=True)],
                "axes": [{"min": None, "max": None, "fmt": "0"}]}
    for t, c, r, p in [("ADP NSA", "R", 115, 1), ("Natural resources and mining (NSA)", "T", 115, 7),
                       ("Construction (NSA)", "U", 131, 1), ("Manufacturing (NSA)", "V", 131, 7),
                       ("Trade, transportation, and utilities (NSA)", "X", 148, 1), ("Information (NSA)", "Y", 148, 7),
                       ("Financial activities (NSA)", "Z", 165, 1), ("Professional and business services (NSA)", "AA", 165, 7),
                       ("Education and health services (NSA)", "AB", 182, 1), ("Leisure and hospitality (NSA)", "AC", 182, 7),
                       ("Other services (NSA)", "AD", 199, 1)]:
        out.append(block(t, c, r, p))
    return out


def validate(D, as_of, expected=None):
    errs = []
    for c in ["U.S."] + SECTORS:
        if as_of not in D.get(c, {}):
            errs.append(f"{c} sem {as_of}")
    if errs:
        return errs
    if expected and as_of < expected:
        errs.append(f"arquivo ainda em {as_of}, esperado {expected}")
    total = D["U.S."][as_of][1]
    soma = sum(D[c][as_of][1] for c in SECTORS)
    if abs(total - soma) > 5000:
        errs.append(f"setores nao fecham: {total} x {soma}")
    prev = D["U.S."].get(calc.shift(as_of, -1))
    if prev is None or abs(total - prev[1]) > 3_000_000:
        errs.append("variacao fora do normal")
    return errs


def render(D, next_list=None, published=None):
    as_of = max(D["U.S."])
    G = build_grid(D, as_of)
    published = published or dt.datetime.now(BRT)
    day = published.date().isoformat()
    upcoming = [d for d in (next_list or []) if d > day]
    state = {"as_of": as_of, "published": published.isoformat(timespec="seconds"), "future": next_list or [],
             "next_release": f"{upcoming[0]}T08:15:00-05:00" if upcoming else None}
    page = bd.fill_template("ADP - Monthly", "adp", "state_adp.json", "", "", as_of, published, charts(D, G, as_of))
    (ROOT / "docs/adp.html").write_text(page, encoding="utf-8")
    json.dump(state, open(ROOT / "docs/state_adp.json", "w"))
    return as_of


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
    print(kv)


def state():
    p = ROOT / "docs/state_adp.json"
    return json.load(open(p)) if p.exists() else {}


def once():
    blob, info = latest_zip()
    D = parse_zip(blob)
    as_of = max(D["U.S."])
    errs = validate(D, as_of)
    if errs:
        print("NAO PUBLICADO:", errs)
        output(changed="false")
        return 1
    if state().get("as_of") == as_of and "--force" not in sys.argv:
        print("Sem novidade.")
        output(changed="false")
        return 0
    render(D, next_dates(info))
    output(changed="true", as_of=as_of)
    return 0


def watch():
    now = dt.datetime.now(ET)
    st = state()
    today = now.date().isoformat()
    if now.time() >= STOP:
        return once()
    if today not in st.get("future", []):
        print("Hoje nao ha ADP.")
        output(changed="false")
        return 0
    expected = calc.shift(today[:7], -1)
    if st.get("as_of", "") >= expected:
        print("Release ja publicado.")
        output(changed="false")
        return 0
    if now.time() < dt.time(7, 45):
        print("Cedo demais; a proxima rodada assume.")
        output(changed="false")
        return 0
    start = now.replace(hour=START.hour, minute=START.minute, second=START.second, microsecond=0)
    if now < start:
        time.sleep((start - now).total_seconds())
    while dt.datetime.now(ET).time() < STOP:
        blob = try_download(dt.datetime.now(ET).date())
        if blob:
            first_seen = dt.datetime.now(BRT)
            try:
                D = parse_zip(blob)
                as_of = max(D["U.S."])
                errs = validate(D, as_of, expected)
            except Exception as e:
                errs, as_of = [f"arquivo invalido: {type(e).__name__}"], None
            if not errs:
                # Nunca publica antes do horario oficial
                while dt.datetime.now(ET).time() < OFFICIAL:
                    time.sleep(1)
                render(D, st.get("future"))
                with open(ROOT / "data/log_adp.jsonl", "a") as f:
                    f.write(json.dumps({"as_of": as_of, "first_seen": first_seen.isoformat(timespec="seconds"),
                                        "built": dt.datetime.now(BRT).isoformat(timespec="seconds")}) + "\n")
                output(changed="true", as_of=as_of)
                return 0
            print("Aguardando conferencia:", errs)
        time.sleep(POLL_SECONDS)
    print("Arquivo nao apareceu ate", STOP)
    output(changed="false")
    return 1


if __name__ == "__main__":
    sys.exit(watch() if "--watch" in sys.argv else once())
