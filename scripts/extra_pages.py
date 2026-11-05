"""Abas de seguro-desemprego, ECI, produtividade, Wage Tracker e expectativas (SCE), direto das fontes.

Cada fonte falha sozinha, mantendo o ultimo dado bom. So publica quando algo mudou.
"""
import csv, datetime as dt, io, json, os, pathlib, re, statistics, sys, time, urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build_dashboard as bd, calc, revelio
from revelio_extras import bar, line

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data/extra_pages.json"
ET = ZoneInfo("America/New_York")
BRT = ZoneInfo("America/Sao_Paulo")
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
DOL = "https://www.dol.gov/ui/data.pdf"
ATL = "https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/wage-growth-tracker/wage-growth-data.xlsx"
SCE = "https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-data.xlsx"
CLAIMS = {"initial": "ICSA", "continuing": "CCSA", "initial_nsa": "ICNSA", "continuing_nsa": "CCNSA"}
ECI = {"comp_yoy": "CIU2010000000000A", "wage_yoy": "CIU2020000000000A", "civ_yoy": "CIU1010000000000A",
       "comp_qoq": "CIS2010000000000Q", "wage_qoq": "CIS2020000000000Q"}
PROD = {"ulc_qoq": "PRS85006112", "prod_qoq": "PRS85006092", "ulc": "PRS85006113", "prod": "PRS85006093"}
PAGES = {"claims": "Unemployment Insurance Claims", "eci": "Employment Cost Index", "productivity": "Productivity and Costs",
         "wagetracker": "Wage Growth Tracker", "sce": "Survey of Consumer Expectations"}
MONTHS3 = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; employment-tracker)", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fred(series):
    text = get(FRED.format(series)).decode("utf-8-sig")
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        v = r.get(series)
        if v not in (None, "", "."):
            out[r["observation_date"]] = float(v)
    return out


def dol_release(blob):
    """Le o release semanal do Departamento do Trabalho: {"initial": (semana, valor), "continuing": (semana, valor)}."""
    from pypdf import PdfReader
    t = re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(blob)).pages[:2]))
    year = int(re.search(r"(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, (20\d\d)", t).group(1))
    def week(name, day):
        m = dt.datetime.strptime(f"{name} {day} {year}", "%B %d %Y").date()
        return (m if m <= dt.date(year, 12, 31) else m).isoformat()
    a = re.search(r"week ending ([A-Z][a-z]+) (\d{1,2}), the advance figure for seasonally adjusted initial claims was ([\d,]+)", t)
    b = re.search(r"unemployment during the week ending ([A-Z][a-z]+) (\d{1,2}) was ([\d,]+)", t)
    if not a or not b:
        raise ValueError("release do DOL fora do padrao")
    return {"initial": (week(a.group(1), a.group(2)), float(a.group(3).replace(",", ""))),
            "continuing": (week(b.group(1), b.group(2)), float(b.group(3).replace(",", "")))}


def fetch_claims(old):
    C = dict(old or {})
    for key, series in CLAIMS.items():
        try:
            s = fred(series)
            if len(s) > 500 and 50_000 < s[max(s)] < 30_000_000:
                C[key] = s
        except Exception as e:
            print("fonte fora:", series, type(e).__name__, e)
    try:
        rel = dol_release(get(DOL))
        for key, (week, value) in rel.items():
            s = C.setdefault(key, {})
            if week in s and s[week] != value:
                print("DOL e serie diferem:", key, week, value, s[week])
            s[week] = value  # o release do DOL e a fonte original
        C["dol_weeks"] = {k: v[0] for k, v in rel.items()}
    except Exception as e:
        print("release do DOL fora:", type(e).__name__, e)
    return C


def fetch_bls(ids, old):
    key = os.environ.get("BLS_API_KEY", "")
    out = dict(old or {})
    if not key:
        return out
    for start, end in ((2006, 2026), ):
        body = {"seriesid": list(ids.values()), "startyear": str(start), "endyear": str(dt.date.today().year), "registrationkey": key}
        req = urllib.request.Request("https://api.bls.gov/publicAPI/v2/timeseries/data/", json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            J = json.load(r)
        if J.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError(str(J.get("message")))
        names = {v: k for k, v in ids.items()}
        for s in J["Results"]["series"]:
            vals = {}
            for d in s["data"]:
                if d["period"].startswith("Q") and d["period"] != "Q05" and d["value"] not in ("", "-"):
                    vals[f"{d['year']}-{d['period']}"] = float(d["value"])
            if vals:
                out[names[s["seriesID"]]] = vals
    return out


def sheet_rows(wb, name):
    return list(wb[name].iter_rows(values_only=True))


def dated_table(rows):
    """Tabela com cabecalho numa linha e a primeira coluna em data: {coluna: {AAAA-MM: valor}}."""
    head, out = None, {}
    for r in rows:
        first = r[0]
        key = None
        if isinstance(first, (dt.datetime, dt.date)):
            key = f"{first.year}-{first.month:02d}"
        elif isinstance(first, (int, float)) and 190000 < first < 210000:
            key = f"{int(first) // 100}-{int(first) % 100:02d}"
        if key is None:
            if first is None and any(isinstance(c, str) for c in r[1:]):
                head = r
            continue
        if head is None:
            continue
        for name, v in zip(head[1:], r[1:]):
            if isinstance(name, str) and isinstance(v, (int, float)):
                out.setdefault(name, {})[key] = float(v)
    return out


def fetch_atlanta(old):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(get(ATL)), read_only=True, data_only=True)
    O = dated_table(sheet_rows(wb, "data_overall"))
    C = dated_table(sheet_rows(wb, "data_chart1"))
    Z = dated_table(sheet_rows(wb, "data_chart3"))
    J = dated_table(sheet_rows(wb, "Job Switcher"))
    Q = dated_table(sheet_rows(wb, "Average Wage Quartile"))
    I = dated_table(sheet_rows(wb, "Industry"))
    out = {"overall": O["Overall"], "raw": C["Overall: Non-smoothed"], "zero": Z["Overall: Percent of zero wage changes"],
           "stayer": J["Job Stayer"], "switcher": J["Job Switcher"],
           "low": Q["Lowest quartile of wage distribution"], "high": Q["Highest quartile of wage distribution"],
           "industry": {k: v for k, v in I.items() if k != "Overall"}}
    if not 0 < out["overall"][max(out["overall"])] < 12:
        raise ValueError("Wage Tracker fora do normal")
    return out


def fetch_sce(old):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(get(SCE)), read_only=True, data_only=True)
    def table(name):
        rows = sheet_rows(wb, name)
        i = next(k for k, r in enumerate(rows) if r[0] is None and any(isinstance(c, str) for c in r[1:]))
        return dated_table(rows[i:])
    F = table("Job finding expectations")
    S = table("Job separation expectation")
    U = table("Unemployment Expectations")
    E = table("Earnings growth")
    pick = lambda T, w: next(v for k, v in T.items() if w in k)
    out = {"finding": pick(F, "finding a job"), "losing": pick(S, "losing a job"), "leaving": pick(S, "leaving a job"),
           "unemployment": pick(U, "higher one year"), "earnings": pick(E, "Median expected earnings")}
    if not 10 < out["finding"][max(out["finding"])] < 90:
        raise ValueError("SCE fora do normal")
    return out


def load():
    return json.load(open(DATA)) if DATA.exists() else {}


def fetch_all():
    D = load()
    for key, fn in (("claims", lambda: fetch_claims(D.get("claims"))), ("eci", lambda: fetch_bls(ECI, D.get("eci"))),
                    ("productivity", lambda: fetch_bls(PROD, D.get("productivity"))),
                    ("wagetracker", lambda: fetch_atlanta(D.get("wagetracker"))), ("sce", lambda: fetch_sce(D.get("sce")))):
        try:
            D[key] = fn()
        except Exception as e:
            print("fonte fora:", key, type(e).__name__, e)
    return D


def label_week(w):
    d = dt.date.fromisoformat(w)
    return f"{d.day:02d}-{MONTHS3[d.month - 1]}-{str(d.year)[2:]}"


def label_q(q):
    return f"{q[-1]}Q{q[2:4]}"


def chart(title, cats, series, row, col=1, date=True, axes=None, sub=None):
    return {"row": row, "col": col, "title": [title] + ([sub] if sub else []), "cats": cats, "date": date, "horizontal": False,
            "series": series, "axes": axes or [{"min": None, "max": None, "fmt": "General"}]}


def tight(*series, fmt="0.0"):
    vals = [v for s in series for v in s if v is not None]
    lo, hi = min(vals), max(vals)
    gap = max((hi - lo) * .12, .1)
    return {"min": round(lo - gap, 1), "max": round(hi + gap, 1), "fmt": fmt}


def ma_list(values, n):
    out = []
    for i in range(len(values)):
        w = values[max(0, i - n + 1): i + 1]
        out.append(sum(w) / n if len(w) == n and None not in w else None)
    return out


def claims_charts(C):
    out = []
    for row, (title, key, name, div) in enumerate([("Initial Claims (SA, thousands)", "initial", "Initial claims", 1000),
                                                   ("Continuing Claims (SA, thousands)", "continuing", "Continuing claims", 1000)]):
        s = C[key]
        weeks = sorted(s)
        vals = [s[w] / div for w in weeks]
        ma4 = ma_list(vals, 4)[-156:]
        b = bar(name, vals[-156:], "A6A6A6", show=False, fmt="0")
        n = len(ma4)
        b["labels"] = [{"i": n - 1, "fmt": "0", "fill": "FFFF00"}]
        out.append(chart(title, [label_week(w) for w in weeks[-156:]], [b, line("4-week average", ma4, "153D64", fmt="0")], 10 + row * 10,
                         axes=[{"min": 0, "max": None, "fmt": "0"}]))
    def seasonal(key):
        s = C[key]
        last = max(s)
        y = int(last[:4])
        table = {}
        for w, v in s.items():
            d = dt.date.fromisoformat(w)
            table.setdefault(d.isocalendar()[1], {})[d.year] = v / 1000
        wk = list(range(1, 53))
        avg = [statistics.mean([table[k][yy] for yy in range(2015, 2020) if yy in table.get(k, {})]) if any(yy in table.get(k, {}) for yy in range(2015, 2020)) else None for k in wk]
        return wk, avg, [table.get(k, {}).get(y - 1) for k in wk], [table.get(k, {}).get(y) for k in wk], y
    for col, (title, key) in zip((1, 7), (("Initial Claims NSA, by week (thousands)", "initial_nsa"), ("Continuing Claims NSA, by week (thousands)", "continuing_nsa"))):
        wk, avg, y0, y1, y = seasonal(key)
        out.append(chart(title, wk, [line("Average 2015-2019", avg, "AEAEAE", label=False, fmt="0"), line(str(y - 1), y0, "215F9A", label=False, fmt="0"),
                                     line(str(y), y1, "C00000", fmt="0")], 40, col, date=False, axes=[{"min": None, "max": None, "fmt": "0"}]))
    return out


def eci_charts(E):
    qs = sorted(E["comp_yoy"])[-44:]
    cats = [label_q(q) for q in qs]
    g = lambda k: [E[k].get(q) for q in qs]
    q2 = sorted(E["comp_qoq"])[-24:]
    return [chart("Employment Cost Index, Private (YoY, %)", cats, [line("Total compensation", g("comp_yoy"), "153D64"), line("Wages and salaries", g("wage_yoy"), "C00000")], 10,
                  axes=[tight(g("comp_yoy"), g("wage_yoy"))]),
            chart("Employment Cost Index, Private (QoQ, SA, %)", [label_q(q) for q in q2],
                  [bar("Total compensation", [E["comp_qoq"].get(q) for q in q2], "156082"), bar("Wages and salaries", [E["wage_qoq"].get(q) for q in q2], "A6CAEC")], 20,
                  axes=[{"min": 0, "max": None, "fmt": "0.0"}])]


def productivity_charts(P):
    def yoy(s):
        out = {}
        for q, v in s.items():
            p = f"{int(q[:4]) - 1}{q[4:]}"
            if p in s:
                out[q] = (v / s[p] - 1) * 100
        return out
    u, p = yoy(P["ulc"]), yoy(P["prod"])
    qs = sorted(u)[-44:]
    q2 = sorted(P["ulc_qoq"])[-16:]
    return [chart("Unit Labor Costs and Productivity, Nonfarm Business (YoY, %)", [label_q(q) for q in qs],
                  [line("Unit labor costs", [u.get(q) for q in qs], "C00000"), line("Productivity", [p.get(q) for q in qs], "153D64")], 10),
            chart("Unit Labor Costs and Productivity (QoQ, SAAR, %)", [label_q(q) for q in q2],
                  [bar("Unit labor costs", [P["ulc_qoq"].get(q) for q in q2], "156082"), bar("Productivity", [P["prod_qoq"].get(q) for q in q2], "A6CAEC")], 20)]


def wage_charts(W):
    months = sorted(W["overall"])
    long = [m for m in months if m >= "2015-01"]
    cats = [bd.month_label(m) for m in long]
    g = lambda k: [W[k].get(m) for m in long]
    out = [chart("Wage Growth Tracker, Overall (YoY, %)", cats, [line("3-month average", g("overall"), "153D64"), line("Monthly", g("raw"), "A6CAEC", label=False)], 10,
                 axes=[tight(g("overall"), g("raw"))]),
           chart("Job Stayers vs. Job Switchers (12-month average, %)", cats, [line("Job stayers", g("stayer"), "153D64"), line("Job switchers", g("switcher"), "C00000")], 20,
                 axes=[tight(g("stayer"), g("switcher"))]),
           chart("Lowest vs. Highest Wage Quartile (12-month average, %)", cats, [line("Lowest quartile", g("low"), "C00000"), line("Highest quartile", g("high"), "153D64")], 30, 1,
                 axes=[tight(g("low"), g("high"))]),
           chart("Workers with Zero Wage Change (%)", cats, [line("Zero wage change", g("zero"), "153D64")], 30, 7, axes=[tight(g("zero"))])]
    I = W["industry"]
    last = max(max(s) for s in I.values())
    names = sorted(I, key=lambda n: -I[n].get(last, 0))
    prev = calc.shift(last, -12)
    out.append({"row": 40, "col": 1, "title": ["Wage Growth by Industry (12-month average, %)"], "cats": names, "date": False, "horizontal": True,
                "series": [bar(bd.month_label(last), [I[n].get(last) for n in names], "156082"), bar(bd.month_label(prev), [I[n].get(prev) for n in names], "A6CAEC")],
                "axes": [{"min": 0, "max": None, "fmt": "0.0"}]})
    return out


def sce_charts(X):
    months = sorted(X["finding"])
    cats = [bd.month_label(m) for m in months]
    g = lambda k: [X[k].get(m) for m in months]
    def one(title, keys, row, col):
        series = [line(n, g(k), c) for n, k, c in keys]
        return chart(title, cats, series, row, col, axes=[tight(*[g(k) for _, k, _ in keys])])
    return [one("Probability of Finding a Job in 3 Months if Lost Today (%)", [("Job finding", "finding", "153D64")], 10, 1),
            one("Probability Unemployment Is Higher in 1 Year (%)", [("Unemployment higher", "unemployment", "C00000")], 10, 7),
            one("Probability of Losing or Leaving a Job in 12 Months (%)", [("Losing a job", "losing", "C00000"), ("Leaving a job", "leaving", "153D64")], 20, 1),
            one("Median Expected Earnings Growth in 1 Year (%)", [("Earnings growth", "earnings", "153D64")], 20, 7)]


def latest(key, D):
    if key == "claims":
        return max(D["claims"]["initial"])
    if key == "eci":
        return max(D["eci"]["comp_yoy"])
    if key == "productivity":
        return max(D["productivity"]["ulc_qoq"])
    if key == "wagetracker":
        return max(D["wagetracker"]["overall"])
    return max(D["sce"]["finding"])


def latest_label(key, v):
    if key == "claims":
        return "Week ending " + label_week(v)
    if key in ("eci", "productivity"):
        return label_q(v)
    return bd.month_label(v)


def render(D, published=None):
    published = published or dt.datetime.now(BRT)
    builders = {"claims": claims_charts, "eci": eci_charts, "productivity": productivity_charts, "wagetracker": wage_charts, "sce": sce_charts}
    for key, fn in builders.items():
        try:
            if key not in D:
                raise KeyError(key)
            v = latest(key, D)
            month = "2000-01"
            page = bd.fill_template(PAGES[key], key, f"state_{key}.json", "", "", month, published, fn(D[key]))
            page = page.replace(f"Latest data: {bd.month_label(month)}", f"Latest data: {latest_label(key, v)}")
            page = page.replace(f"const ASOF='{month}'", f"const ASOF='{v}'")
            (ROOT / f"docs/{key}.html").write_text(page, encoding="utf-8")
            json.dump({"as_of": v, "published": published.isoformat(timespec="seconds"), "next_release": None}, open(ROOT / f"docs/state_{key}.json", "w"))
        except Exception as e:
            print("pagina fora:", key, type(e).__name__, e)


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
    print(kv)


def publish_if_changed(D, force=False):
    old = load()
    if D == old and not force:
        print("Sem novidade.")
        output(changed="false")
        return
    json.dump(D, open(DATA, "w"), separators=(",", ":"))
    render(D)
    output(changed="true")


def watch_claims():
    """Quinta: espera 8:30 ET e consulta o release do DOL ate sair a semana nova."""
    now = dt.datetime.now(ET)
    old = load()
    have = max(old.get("claims", {}).get("initial", {"0": 0}))
    if now.weekday() != 3:
        return False
    official = now.replace(hour=8, minute=30, second=0, microsecond=0)
    # Nas quintas de Revelio, deixa a publicacao dele sair primeiro
    if now.date().isoformat() in revelio.RELEASE_DATES:
        official = official.replace(minute=36)
    if now < official - dt.timedelta(minutes=40) or now > official + dt.timedelta(minutes=60):
        return False
    if now < official:
        time.sleep((official - now).total_seconds())
    stop = official + dt.timedelta(minutes=45)
    while dt.datetime.now(ET) < stop:
        try:
            rel = dol_release(get(DOL + f"?t={int(time.time())}"))
            if rel["initial"][0] > have:
                return True
        except Exception as e:
            print("aguardando:", type(e).__name__, e)
        time.sleep(10)
    return True


if __name__ == "__main__":
    force = "--force" in sys.argv
    if "--watch" in sys.argv:
        watch_claims()
    publish_if_changed(fetch_all(), force)
