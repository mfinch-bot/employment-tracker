"""Pagina do Revelio: mesmas contas do Revelio Employment.xlsx, com os CSVs publicos do RPLS.

Os CSVs ficam na pasta do mes antes da hora oficial. Por isso o robo nunca abre a pasta de um mes
ainda nao divulgado: so le o arquivo a partir de 8:30 ET e nunca publica antes disso.

Modos:
  --watch  no dia do release, espera 8:30 ET e publica assim que o site confirmar o numero
  --once   le o mes que o site ja mostra como divulgado
"""
import csv, datetime as dt, io, json, os, pathlib, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import adp, build_dashboard as bd, calc

ROOT = pathlib.Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
BRT = ZoneInfo("America/Sao_Paulo")
PAGE = "https://www.reveliolabs.com/public-labor-statistics/employment"
FILES = "https://info0.s3.us-east-2.amazonaws.com/rpls/{}/employment/{}"
DATA = ROOT / "data/revelio.json"
RELEASE_DATES = ["2026-11-05", "2026-12-03"]
OFFICIAL = dt.time(8, 30)
WAIT_SITE = dt.time(8, 32)
STOP = dt.time(9, 30)
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
CODES = ["11", "21", "22", "23", "31-33", "42", "44-45", "48-49", "51", "52-53", "54-56", "61", "62", "71-72", "81", "92", "99"]
SECTORS = [("Mining and Logging", ["21"]), ("Construction", ["23"]), ("Manufacturing", ["31-33"]),
           ("Trade, Transportation, and Utilities", ["22", "42", "44-45", "48-49"]), ("Information", ["51"]),
           ("Financial Activities", ["52-53"]), ("Professional and Business Services", ["54-56"]),
           ("Education and Health Services", ["61", "62"]), ("Leisure and Hospitality", ["71-72"]),
           ("Other Services", ["81"]), ("Government", ["92"])]
HIGH_IMMIGRANT = ["23", "31-33", "42", "48-49", "54-56", "71-72", "81"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; employment-tracker)",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def site_release():
    """Mes e numero que o titulo da pagina do Revelio mostra como divulgados. None se nao conseguir ler."""
    try:
        text = get(f"{PAGE}?t={int(time.time())}").decode("utf-8", "replace")
    except Exception as e:
        print("site sem resposta:", type(e).__name__)
        return None
    t = re.search(r"<title[^>]*>([^<]*)</title>", text)
    m = re.search(r"([A-Z][a-z]+)\s+(\d{4})", t.group(1)) if t else None
    if not m or m.group(1) not in MONTH_NAMES:
        print("titulo fora do padrao")
        return None
    v = re.search(r"([-−–]?\d[\d.,]*)\s*K\s+Jobs?\s+(\w+)", t.group(1), re.I)
    value = None
    if v:
        value = float(v.group(1).replace(",", "").replace("−", "-").replace("–", "-"))
        if re.match(r"(lost|shed|cut|decline|fell)", v.group(2), re.I):
            value = -abs(value)
    return {"month": f"{m.group(2)}-{MONTH_NAMES.index(m.group(1)) + 1:02d}", "value": value}


def parse(national, naics):
    """Devolve {"national": {mes: [NSA, SA]}, "naics": {codigo: {mes: [NSA, SA]}}}."""
    D = {"national": {}, "naics": {}}
    for r in csv.DictReader(io.StringIO(national)):
        D["national"][r["month"]] = [int(r["employment_nsa"]), int(r["employment_sa"])]
    for r in csv.DictReader(io.StringIO(naics)):
        D["naics"].setdefault(r["naics2d_code"], {})[r["month"]] = [int(r["employment_nsa"]), int(r["employment_sa"])]
    return D


def validate(D, month, site=None):
    errs = []
    as_of = max(D["national"])
    if as_of != month:
        errs.append(f"arquivo em {as_of}, esperado {month}")
        return errs
    if sorted(D["naics"]) != sorted(CODES):
        errs.append(f"setores diferentes do esperado: {sorted(D['naics'])}")
        return errs
    prev = calc.shift(month, -1)
    for i, k in ((0, "NSA"), (1, "SA")):
        soma = sum(D["naics"][c][month][i] for c in CODES)
        if abs(soma - D["national"][month][i]) > 1000:
            errs.append(f"setores nao fecham ({k}): {soma} x {D['national'][month][i]}")
    head = (D["national"][month][1] - D["national"][prev][1]) / 1000
    if abs(head) > 1500:
        errs.append(f"variacao fora do normal: {head:.1f}")
    if site and site["month"] == month and site["value"] is not None and abs(head - site["value"]) > 0.11:
        errs.append(f"arquivo {head:.1f} x site {site['value']}")
    return errs


def fetch(month, site=None):
    """Baixa os CSVs da pasta do mes. So chamar para mes divulgado ou depois de 8:30 ET do dia do release."""
    folder = month.replace("-", "")
    D = parse(get(FILES.format(folder, "employment_national.csv")).decode("utf-8-sig"),
              get(FILES.format(folder, "employment_naics.csv")).decode("utf-8-sig"))
    errs = validate(D, month, site)
    if errs:
        raise ValueError("; ".join(errs))
    return D


def series(D):
    """Variacao mensal em milhares, com os mesmos agregados do Excel."""
    months = sorted(D["national"])
    def lvl(codes, i):
        return {m: sum(D["naics"][c][m][i] for c in codes) for m in months}
    level = {"total": {m: D["national"][m][1] for m in months}, "total_nsa": {m: D["national"][m][0] for m in months}}
    level["government"] = lvl(["92"], 1)
    level["health"] = lvl(["62"], 1)
    level["private"] = {m: level["total"][m] - level["government"][m] - D["naics"]["11"][m][1] - D["naics"]["99"][m][1]
                        for m in months}
    level["high"] = lvl(HIGH_IMMIGRANT, 1)
    for name, codes in SECTORS:
        level[name] = lvl(codes, 1)
    S = {k: {m: (v[m] - v[calc.shift(m, -1)]) / 1000 for m in months if calc.shift(m, -1) in v} for k, v in level.items()}
    S["ex"] = {m: S["total"][m] - S["government"][m] - S["health"][m] for m in S["total"]}
    S["low"] = {m: S["total"][m] - S["high"][m] for m in S["total"]}
    return S


def mma(s, m):
    vals = [s.get(calc.shift(m, -i)) for i in range(3)]
    return None if None in vals else sum(vals) / 3


def quarter(m):
    return f"{(int(m[5:]) - 1) // 3 + 1}Q{m[:4]}"


def charts(D):
    bars, line = adp.bars, adp.line
    S = series(D)
    as_of = max(D["national"])
    y1 = int(as_of[:4])
    M = calc.MONTHS
    months = sorted(S["total"])
    n = len(months)
    cats = [bd.month_label(m) for m in months]
    def history(title, row, key, name, lo, hi, yellow=False):
        b = bars(name, [S[key][m] for m in months], "A6A6A6", show=False)
        b["labels"] = [{"i": n - 13, "fmt": None, "fill": None}, {"i": n - 2, "fmt": None, "fill": None},
                       {"i": n - 1, "fmt": None, "fill": "FFFF00" if yellow else None}]
        return {"row": row, "col": 1, "title": [title], "cats": cats, "date": True, "horizontal": False,
                "series": [b, line("3MMA", [mma(S[key], m) for m in months], "153D64", labels=[{"i": n - 1, "fmt": None, "fill": None}])],
                "axes": [{"min": lo, "max": hi, "fmt": "General"}]}
    out = [history("Nonfarm Payroll", 19, "total", "Nonfarm Payroll Increase", -200, 1000, yellow=True)]
    def year(key, y):
        return [S[key].get(f"{y}-{i:02d}") for i in range(1, 13)]
    out.append({"row": 38, "col": 1, "title": ["Nonfarm Payroll Increase NSA"], "cats": M, "date": False, "horizontal": False,
                "series": [bars(str(y1 - 1), year("total_nsa", y1 - 1), "A6CAEC", show=False), bars(str(y1), year("total_nsa", y1), "156082", show=False)],
                "axes": [{"min": None, "max": None, "fmt": "0"}]})
    mm = as_of[5:]
    years = [y for y in range(2021, y1 + 1) if f"{y}-{mm}" in S["total_nsa"]]
    out.append({"row": 38, "col": 7, "title": [f"Nonfarm Payroll Increase NSA - {M[int(mm) - 1]}"], "cats": years, "date": False,
                "horizontal": False, "series": [bars(None, [S["total_nsa"][f"{y}-{mm}"] for y in years], "156082")],
                "axes": [{"min": None, "max": None, "fmt": "0"}]})
    out.append(history("Private Payroll", 57, "private", "Private Payroll Increase", -200, 1000))
    out.append(history("Payroll Ex Government & Health", 74, "ex", "Payroll Ex Government & Health Increase", -200, 1000))
    out.append(history("Government Payroll", 92, "government", "Government Payroll Increase", -150, 150))
    out.append(history("Health Payroll", 110, "health", "Health Payroll Increase", -30, 150))
    names = [a for a, _ in SECTORS]
    out.append({"row": 128, "col": 1, "title": ["Payroll Breakdown by Sector"], "cats": names, "date": False, "horizontal": True,
                "series": [bars(M[int(mm) - 1], [S[a][as_of] for a in names], "156082"),
                           bars("Prior month", [S[a][calc.shift(as_of, -1)] for a in names], "A6CAEC")],
                "axes": [{"min": None, "max": None, "fmt": "General"}]})
    quarters = []
    q, last = as_of, None
    while len(quarters) < 5:
        if quarter(q) != last:
            quarters.append(quarter(q))
            last = quarter(q)
        q = calc.shift(q, -1)
    colors = ["3B7D23", "A9D18E", "A6A6A6", "A6CAEC", "153D64"]
    qseries = []
    for label, color in zip(reversed(quarters), colors):
        ms = [m for m in months if quarter(m) == label]
        qseries.append(bars(label, [sum(S[a][m] for m in ms) / len(ms) for a in names], color, show=False))
    out.append({"row": 147, "col": 1, "title": ["Payroll by Sector", "(Quarterly average)"], "cats": names, "date": False,
                "horizontal": False, "series": qseries, "axes": [{"min": None, "max": None, "fmt": "0"}]})
    ms3 = months[2:]
    def imm(key):
        return [mma(S[key], m) for m in ms3]
    out.append({"row": 165, "col": 1, "title": ["Payroll sectors: highest vs. lowest share of immigrants (3mma)"],
                "cats": [bd.month_label(m) for m in ms3], "date": True, "horizontal": False,
                "series": [line("High immigrant share", imm("high"), "153D64", labels=[{"i": len(ms3) - 1, "fmt": None, "fill": None}]),
                           line("Low immigrant share", imm("low"), "A6CAEC", labels=[{"i": len(ms3) - 1, "fmt": None, "fill": None}])],
                "axes": [{"min": -50, "max": 260, "fmt": "0"}]})
    blocks = [("Payroll Employment", "total"), ("Private Payroll", "private"), ("Mining and Logging", "Mining and Logging"),
              ("Construction", "Construction"), ("Manufacturing", "Manufacturing"),
              ("Trade, Transportation, and Utilities", "Trade, Transportation, and Utilities"), ("Information", "Information"),
              ("Financial Activities", "Financial Activities"), ("Professional and Business Services", "Professional and Business Services"),
              ("Education and Health Services", "Education and Health Services"), ("Leisure and Hospitality", "Leisure and Hospitality"),
              ("Other Services", "Other Services"), ("Government", "government"), ("Health", "health")]
    for i, (t, key) in enumerate(blocks):
        out.append({"row": 184 + (i // 2) * 18, "col": 1 if i % 2 == 0 else 7, "title": [t], "cats": M, "date": False, "horizontal": False,
                    "series": [line(str(y1 - 1), year(key, y1 - 1), "215F9A", marker=True), line(str(y1), year(key, y1), "C00000", marker=True)],
                    "axes": [{"min": None, "max": None, "fmt": "General"}]})
    return out


def render(D, published=None):
    as_of = max(D["national"])
    published = published or dt.datetime.now(BRT)
    page = bd.fill_template("Revelio Employment", "revelio", "state_revelio.json", "", "", as_of, published, charts(D))
    (ROOT / "docs/revelio.html").write_text(page, encoding="utf-8")
    json.dump({"as_of": as_of, "published": published.isoformat(timespec="seconds"), "next_release": None},
              open(ROOT / "docs/state_revelio.json", "w"))
    return as_of


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
    print(kv)


def load():
    return json.load(open(DATA)) if DATA.exists() else None


def publish(D, month, first_seen=None, site=None):
    json.dump(D, open(DATA, "w"), separators=(",", ":"))
    render(D)
    if first_seen:
        with open(ROOT / "data/log_revelio.jsonl", "a") as f:
            f.write(json.dumps({"as_of": month, "first_seen": first_seen.isoformat(timespec="seconds"),
                                "built": dt.datetime.now(BRT).isoformat(timespec="seconds"),
                                "site_confirmed": bool(site and site["month"] == month)}) + "\n")
    output(changed="true", as_of=month)


def once():
    site = site_release()
    old = load()
    month = site["month"] if site else (max(old["national"]) if old else None)
    if month is None:
        print("Nao consegui saber o mes divulgado.")
        output(changed="false")
        return 1
    D = fetch(month, site)
    if D == old and "--force" not in sys.argv:
        print("Sem novidade.")
        output(changed="false")
        return 0
    publish(D, month)
    return 0


def watch():
    now = dt.datetime.now(ET)
    old = load()
    have = max(old["national"]) if old else "0000-00"
    today = now.date().isoformat()
    if now.time() < OFFICIAL and today not in RELEASE_DATES:
        print("Hoje nao ha release.")
        output(changed="false")
        return 0
    if today not in RELEASE_DATES:
        # Rodada de seguranca: o site ja mostra um mes novo fora da data prevista
        site = site_release()
        if not site or site["month"] <= have:
            print("Nada novo.")
            output(changed="false")
            return 0
        publish(fetch(site["month"], site), site["month"], dt.datetime.now(BRT), site)
        return 0
    expected = calc.shift(today[:7], -1)
    if have >= expected:
        print("Mes ja publicado.")
        output(changed="false")
        return 0
    official = now.replace(hour=OFFICIAL.hour, minute=OFFICIAL.minute, second=0, microsecond=0)
    if now < official:
        time.sleep((official - now).total_seconds())
    while True:
        t = dt.datetime.now(ET).time()
        try:
            site = site_release()
            confirmed = bool(site and site["month"] >= expected)
            if confirmed or t >= WAIT_SITE:
                month = site["month"] if confirmed else expected
                publish(fetch(month, site), month, dt.datetime.now(BRT), site)
                return 0
        except Exception as e:
            print("aguardando:", type(e).__name__, e)
        if t >= STOP:
            print("Relatorio nao apareceu ate", STOP)
            output(changed="false")
            return 0
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(watch() if "--watch" in sys.argv else once())
