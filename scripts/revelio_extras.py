"""Demais secoes do RPLS: worker type, ocupacoes, vagas, contratacoes, salarios e demissoes em massa.

Nada aqui pode atrapalhar o headline: cada arquivo e cada secao falham sozinhos, mantendo o ultimo dado bom.
"""
import csv, io, json, pathlib, statistics
import calc, build_dashboard as bd

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = "https://info0.s3.us-east-2.amazonaws.com/rpls/{}/{}"
SKIP = {"Unclassified", "Unknown/Other"}
SHORT = {"Agriculture, Forestry, Fishing and Hunting": "Agriculture", "Mining, Quarrying, and Oil and Gas Extraction": "Mining",
         "Other Services (except Public Administration)": "Other Services", "Health Care and Social Assistance": "Health Care",
         "Building and Grounds Cleaning and Maintenance": "Building and Grounds Maintenance",
         "Arts, Design, Entertainment, Sports, and Media": "Arts, Design, Entertainment and Media",
         "Healthcare Practitioners and Technical": "Healthcare Practitioners"}


def tight(*series):
    """Eixo que nao comeca no zero, para series em nivel."""
    vals = [v for s in series for v in s if v is not None]
    lo, hi = min(vals), max(vals)
    gap = max((hi - lo) * .15, .1)
    return {"min": round(lo - gap, 1), "max": round(hi + gap, 1), "fmt": "0.0"}


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def number(s):
    return float(str(s).replace(",", "").replace("$", ""))


def parse_all(texts):
    """texts: {nome do arquivo: conteudo}. So devolve as chaves que deram certo."""
    X = {}
    def run(key, name, fn):
        if name not in texts:
            return
        try:
            X[key] = fn(rows(texts[name]))
        except Exception as e:
            print("arquivo fora:", name, type(e).__name__, e)
    def by(rows_, name, field):
        out = {}
        for r in rows_:
            if r[name] not in SKIP and r[field] != "":
                out.setdefault(SHORT.get(r[name], r[name]), {})[r["month"]] = number(r[field])
        return out
    def worker(rs):
        out = {}
        for r in rs:
            out.setdefault(r["month"], {})[r["foreign_worker_indicator"]] = number(r["employment_sa"])
        return out
    run("worker", "employment/employment_foreign_domestic_workers.csv", worker)
    run("occupation", "employment/employment_soc.csv", lambda rs: by(rs, "soc2d_name", "employment_sa"))
    run("postings", "postings/postings_total_us.csv", lambda rs: {r["month"]: number(r["active_postings_sa"]) for r in rs})
    run("postings_sector", "postings/postings_by_sector.csv", lambda rs: by(rs, "naics2d_name", "active_postings_sa"))
    run("flows", "hiring_attrition/hiring_and_attrition_total_us.csv",
        lambda rs: {r["month"]: [number(r["rl_hiring_rate"]) * 100, number(r["rl_attrition_rate"]) * 100] for r in rs})
    run("hiring_sector", "hiring_attrition/hiring_and_attrition_by_sector.csv", lambda rs: by(rs, "naics2d_name", "rl_hiring_rate"))
    run("attrition_sector", "hiring_attrition/hiring_and_attrition_by_sector.csv", lambda rs: by(rs, "naics2d_name", "rl_attrition_rate"))
    run("salary", "salaries/salaries_national.csv", lambda rs: {r["month"]: number(r["salary_sa"]) for r in rs})
    run("salary_sector", "salaries/salaries_naics.csv", lambda rs: by(rs, "naics2d_name", "salary_sa"))
    run("layoffs", "layoffs/total_layoffs.csv",
        lambda rs: {r["month"]: [number(r["num_employees_notified"]), number(r["num_employees_laidoff"])] for r in rs})
    run("layoffs_sector", "layoffs/layoffs_by_naics.csv", lambda rs: by(rs, "naics2d_name", "num_employees_notified"))
    return X


NAMES = ["employment/employment_foreign_domestic_workers.csv", "employment/employment_soc.csv",
         "postings/postings_total_us.csv", "postings/postings_by_sector.csv",
         "hiring_attrition/hiring_and_attrition_total_us.csv", "hiring_attrition/hiring_and_attrition_by_sector.csv",
         "salaries/salaries_national.csv", "salaries/salaries_naics.csv",
         "layoffs/total_layoffs.csv", "layoffs/layoffs_by_naics.csv"]


def fetch(get, month, old):
    """So chamar depois da hora oficial: le a pasta do mes."""
    folder = month.replace("-", "")
    texts = {}
    for name in NAMES:
        try:
            texts[name] = get(FILES.format(folder, name)).decode("utf-8-sig")
        except Exception as e:
            print("arquivo fora:", name, type(e).__name__, e)
    X = dict(old or {})
    X.update(parse_all(texts))
    return X


def bar(name, data, color, show=True, fmt="0.0"):
    return {"name": name, "type": "bar", "data": data, "color": color, "fill": color, "dash": None, "width": None, "noline": True,
            "marker": None, "markerColor": None, "show": show, "labels": [], "fmt": fmt, "yAxis": 0}


def line(name, data, color, axis=0, label=True, fmt="0.0"):
    last = max((i for i, v in enumerate(data) if v is not None), default=None)
    return {"name": name, "type": "line", "data": data, "color": color, "fill": None, "dash": None, "width": 2.25, "noline": False,
            "marker": ["none", None], "markerColor": None, "show": False,
            "labels": [{"i": last, "fmt": fmt, "fill": None}] if label and last is not None else [], "fmt": fmt, "yAxis": axis}


def dated(title, months, series, axes=None, sub=None):
    t = [title] + ([sub] if sub else [])
    return {"title": t, "cats": [bd.month_label(m) for m in months], "date": True, "horizontal": False, "series": series,
            "axes": axes or [{"min": None, "max": None, "fmt": "General"}]}


def hbars(title, names, series, sub=None):
    t = [title] + ([sub] if sub else [])
    return {"title": t, "cats": names, "date": False, "horizontal": True, "series": series, "tall": len(names) > 12,
            "axes": [{"min": None, "max": None, "fmt": "General"}]}


def ma(s, m, n=3):
    vals = [s.get(calc.shift(m, -i)) for i in range(n)]
    return None if None in vals else sum(vals) / n


def yoy(s, m):
    a, b = s.get(m), s.get(calc.shift(m, -12))
    return None if not a or not b else (a / b - 1) * 100


def sorted_bars(values):
    return [k for k, v in sorted(values.items(), key=lambda kv: -kv[1])]


def worker_section(X):
    W = X["worker"]
    all_m = sorted(W)
    months = all_m[-36:]
    f = {m: W[m]["Foreign workers"] for m in all_m}
    u = {m: W[m]["US workers"] for m in all_m}
    def diff(s):
        return {m: (s[m] - s[calc.shift(m, -1)]) / 1000 for m in s if calc.shift(m, -1) in s}
    df, du = diff(f), diff(u)
    share = [f[m] / (f[m] + u[m]) * 100 for m in months]
    return [dated("Foreign vs. US workers (3MMA)", months, [line("Foreign workers", [ma(df, m) for m in months], "C00000"),
                                                           line("US workers", [ma(du, m) for m in months], "153D64")]),
            dated("Foreign workers share of employment (%)", months,
                  [line("Foreign workers share", share, "C00000", fmt="0.00")], axes=[tight(share)])]


def occupation_section(X):
    O = X["occupation"]
    m = max(max(s) for s in O.values())
    d = {n: (s[m] - s[calc.shift(m, -12)]) / 1000 for n, s in O.items() if m in s and calc.shift(m, -12) in s}
    names = sorted_bars(d)
    return [hbars("Employment by Occupation", names, [bar("12-month change", [d[n] for n in names], "156082")], sub="(12-month change, thousands)")]


def postings_section(X, jolts):
    P = X["postings"]
    months = sorted(P)[-48:]
    J = jolts.get("JTS000000000000000JOL", {})
    rev = [P[m] / 1e6 for m in months]
    jol = [J[m] / 1000 if m in J else None for m in months]
    out = [dated("Job Openings: Revelio vs. JOLTS (millions)", months,
                 [line("Revelio active postings", rev, "C00000", fmt="0.0"), line("JOLTS (rhs)", jol, "153D64", axis=1, fmt="0.0")],
                 axes=[tight(rev), tight(jol)])]
    S = X["postings_sector"]
    m = max(P)
    d = {n: yoy(s, m) for n, s in S.items() if yoy(s, m) is not None}
    names = sorted_bars(d)
    out.append(hbars("Job Openings by Sector", names, [bar("YoY", [d[n] for n in names], "156082")], sub="(YoY, %)"))
    return out


def flows_section(X, jolts):
    F = X["flows"]
    months = sorted(F)[-48:]
    H, E = jolts.get("JTS000000000000000HIL", {}), jolts.get("CES0000000001", {})
    rate = {m: H[m] / E[m] * 1200 for m in H if m in E and E[m]}
    h = {m: F[m][0] for m in F}
    a = {m: F[m][1] for m in F}
    mh, ma_ = [ma(h, m) for m in months], [ma(a, m) for m in months]
    mj = [ma(rate, m) for m in months]
    out = [dated("Hiring and Attrition Rates (annualized, %, 3MMA)", months,
                 [line("Hiring rate", mh, "153D64"), line("Attrition rate", ma_, "C00000")], axes=[tight(mh, ma_)]),
           dated("Hiring Rate: Revelio vs. JOLTS (annualized, %, 3MMA)", months,
                 [line("Revelio", mh, "C00000"), line("JOLTS (rhs)", mj, "153D64", axis=1)], axes=[tight(mh), tight(mj)])]
    m = max(F)
    HS, AS = X["hiring_sector"], X["attrition_sector"]
    v = {n: ma(HS[n], m) * 100 for n in HS if n in AS and ma(HS[n], m) is not None and ma(AS[n], m) is not None}
    names = sorted_bars(v)
    out.append(hbars("Hiring and Attrition Rates by Sector", names,
                     [bar("Hiring rate", [v[n] for n in names], "156082", show=False),
                      bar("Attrition rate", [ma(AS[n], m) * 100 for n in names], "A6CAEC", show=False)], sub="(annualized, %, 3MMA)"))
    return out


def salary_section(X, raw):
    P = X["salary"]
    months = [m for m in sorted(P) if calc.shift(m, -12) in P][-48:]
    A = raw.get("CES0500000003", {})
    out = [dated("New Job Postings Salaries vs. Average Hourly Earnings (YoY, %)", months,
                 [line("Revelio salaries (3MMA)", [ma({k: yoy(P, k) for k in months if yoy(P, k) is not None}, m) for m in months], "C00000"),
                  line("Average Hourly Earnings", [yoy(A, m) for m in months], "153D64")],
                 axes=[{"min": None, "max": None, "fmt": "0.0"}])]
    S = X["salary_sector"]
    m = max(P)
    d = {n: yoy(s, m) for n, s in S.items() if yoy(s, m) is not None}
    names = sorted_bars(d)
    out.append(hbars("Salaries by Sector", names, [bar("YoY", [d[n] for n in names], "156082")], sub="(New job postings, YoY, %)"))
    return out


def layoffs_section(X):
    L = X["layoffs"]
    months = sorted(L)[-36:]
    n = {m: L[m][0] / 1000 for m in L}
    b = bar("Employees notified", [n[m] for m in months], "A6A6A6", show=False)
    out = [dated("Mass Layoff Notices (WARN, thousands)", months, [b, line("3MMA", [ma(n, m) for m in months], "153D64")],
                 axes=[{"min": 0, "max": None, "fmt": "0"}])]
    S = X["layoffs_sector"]
    m = max(L)
    cur = [calc.shift(m, -i) for i in range(12)]
    old = [calc.shift(m, -i) for i in range(12, 24)]
    v = {k: sum(s.get(x, 0) for x in cur) / 1000 for k, s in S.items()}
    w = {k: sum(s.get(x, 0) for x in old) / 1000 for k, s in S.items()}
    names = sorted_bars(v)[:10]
    out.append(hbars("Mass Layoff Notices by Sector (thousands)", names,
                     [bar("Last 12 months", [v[k] for k in names], "156082"), bar("Previous 12 months", [w[k] for k in names], "A6CAEC")]))
    return out


def sections(X):
    def load_json(name):
        try:
            return json.load(open(ROOT / name))
        except Exception:
            return {}
    jolts, raw = load_json("data/raw_jolts.json"), load_json("data/raw.json")
    out = []
    for title, fn in (("Foreign and US workers", lambda: worker_section(X)), ("Occupations", lambda: occupation_section(X)),
                      ("Job Openings", lambda: postings_section(X, jolts)), ("Hiring and Attrition", lambda: flows_section(X, jolts)),
                      ("Salaries", lambda: salary_section(X, raw)), ("Mass Layoff Notices", lambda: layoffs_section(X))):
        try:
            charts = fn()
            charts[0]["section"] = title
            out.append(charts)
        except Exception as e:
            print("secao fora:", title, type(e).__name__, e)
    return out
