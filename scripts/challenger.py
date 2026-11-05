"""Pagina do Challenger: le o relatorio mensal direto do site da Challenger, Gray & Christmas.

Modos:
  --watch  consulta o site a partir de 5:25 ET e publica assim que o relatorio aparecer
  --once   confere uma vez e publica se houver mes novo
"""
import datetime as dt, html, io, json, os, pathlib, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build_dashboard as bd, calc, challenger_detail as detail

ROOT = pathlib.Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
BRT = ZoneInfo("America/Sao_Paulo")
POSTS = "https://www.challengergray.com/wp-json/wp/v2/posts?categories=61&per_page=2&_fields=date_gmt,link,title,content"
# Abr-24 corrigido em 04/11/2026: 64.789 (relatorios de mai-24 e mai-25), a base trazia o valor de abr-25
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
START = dt.time(5, 25)
STOP = dt.time(8, 30)
DATA = ROOT / "data/challenger.json"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; employment-tracker)",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def num(s):
    return int(s.replace(",", ""))


def parse_report(text_post, pdf_text):
    """Devolve mes (AAAA-MM), cortes, contratacoes e governo. Levanta erro se algo nao fechar."""
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text_post)))
    m = re.search(r"announced ([\d,]+) job cuts in ([A-Z][a-z]+)", plain)
    if not m:
        raise ValueError("texto do relatorio fora do padrao")
    cuts_post, month = num(m.group(1)), m.group(2)
    if month not in MONTH_NAMES:
        raise ValueError("mes do relatorio nao identificado")
    five = re.findall(r"(?m)^TOTAL\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", pdf_text)
    if not five:
        raise ValueError("tabela de cortes nao encontrada")
    cuts = num(five[0][2])
    if cuts != cuts_post:
        raise ValueError(f"cortes nao batem: {cuts} x {cuts_post}")
    gov = re.findall(r"(?m)^Government\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", pdf_text)
    if not gov:
        raise ValueError("linha de Government nao encontrada")
    gov_m = num(gov[0][2])
    # O texto nem sempre traz a contratacao na mesma frase: a fonte e a ultima tabela do PDF
    # (mes, acumulado do ano, acumulado do ano anterior), conferida com o acumulado da tabela anual.
    hires = re.findall(r"(?m)^TOTAL\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", pdf_text)
    annual = re.findall(r"(?m)^TOTAL\s+([\d,]+)(?:\s+[\d,]+){5,}\s*$", pdf_text)
    if not hires or not annual:
        raise ValueError("tabela de contratacoes nao encontrada")
    hire, hire_ytd = num(hires[-1][0]), num(hires[-1][1])
    # No 4o trimestre tambem ha a tabela de contratacoes sazonais, com o mesmo formato da anual
    if hire_ytd not in [num(a) for a in annual]:
        raise ValueError(f"contratacoes nao batem: {hire_ytd} x {annual}")
    h = re.search(r"plans to hire ([\d,]+) workers in " + month, plain)
    if h and num(h.group(1)) != hire:
        raise ValueError(f"contratacoes nao batem com o texto: {hire} x {h.group(1)}")
    return month, cuts, hire, gov_m


LAST_PDF = {}


def pdf_text(url):
    from pypdf import PdfReader
    blob = get(url)
    LAST_PDF["blob"] = blob
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(blob)).pages)


def latest_report(expected=None):
    posts = json.loads(get(f"{POSTS}&_={int(time.time())}"))
    for p in posts:
        links = re.findall(r'href="([^"]+\.pdf)"', p["content"]["rendered"])
        if not links:
            continue
        if expected:
            # So baixa o PDF quando o texto ja fala do mes esperado
            name = MONTH_NAMES[int(expected[5:]) - 1]
            if not re.search(rf"job cuts in\s+{name}", html.unescape(re.sub(r"<[^>]+>", " ", p["content"]["rendered"]))):
                raise ValueError("relatorio do mes ainda nao saiu")
        month, cuts, hire, gov = parse_report(p["content"]["rendered"], pdf_text(links[0]))
        pub = dt.datetime.fromisoformat(p["date_gmt"]).replace(tzinfo=dt.timezone.utc)
        year = pub.year if MONTH_NAMES.index(month) + 1 <= pub.month else pub.year - 1
        return f"{year}-{MONTH_NAMES.index(month) + 1:02d}", {"cuts": cuts, "hire": hire, "gov": gov}
    raise ValueError("sem relatorio com PDF")


def load():
    return json.load(open(DATA))


def series(data):
    S = {"cuts": {}, "hire": {}, "gov": {}, "private": {}}
    for m, r in data.items():
        for k in ("cuts", "hire", "gov"):
            if r.get(k) is not None:
                S[k][m] = r[k] / 1000
        if r.get("cuts") is not None and r.get("gov") is not None:
            S["private"][m] = (r["cuts"] - r["gov"]) / 1000
    return S


def monthly_table(s, as_of):
    y = int(as_of[:4])
    out = {"y2": [], "y1": [], "y0": [], "p20": [], "med": [], "p80": []}
    for mm in range(1, 13):
        for k, yr in (("y2", y - 2), ("y1", y - 1), ("y0", y)):
            out[k].append(s.get(f"{yr}-{mm:02d}"))
        vals = [v for m, v in s.items() if int(m[5:]) == mm and 2012 <= int(m[:4]) <= 2019]
        for k, p in (("p20", .2), ("med", .5), ("p80", .8)):
            out[k].append(calc.percentile(vals, p))
    return out


def line(name, data, color, dash=None, marker=False, labels=None):
    return {"name": name, "type": "line", "data": data, "color": color, "fill": None, "dash": dash, "width": 2.25,
            "noline": False, "marker": ["circle", 5] if marker else ["none", None], "markerColor": None, "show": False,
            "labels": labels or [], "fmt": "0.0", "yAxis": 0}


def charts(data, as_of):
    S = series(data)
    y, last = int(as_of[:4]), int(as_of[5:]) - 1
    out = []
    for row, (title, key) in enumerate([("Challenger job cuts", "cuts"), ("Private", "private"), ("Government", "gov"),
                                        ("Hiring offers", "hire")]):
        t = monthly_table(S[key], as_of)
        out.append({"row": row // 2 * 10 + 5, "col": 1 + row % 2 * 6, "title": [title], "cats": calc.MONTHS, "date": False, "horizontal": False,
                    "series": [line("p20", t["p20"], "AEAEAE", "sysDot"), line("med", t["med"], "AEAEAE"),
                               line("p80", t["p80"], "AEAEAE", "sysDot"), line(str(y - 2), t["y2"], "92D050", marker=True),
                               line(str(y - 1), t["y1"], "0E2841", marker=True),
                               line(str(y), t["y0"], "C00000", marker=True, labels=[{"i": last, "fmt": "0.0", "fill": None}])],
                    "axes": [{"min": None, "max": None, "fmt": "0"}]})
    return out


def top(values, n):
    return [k for k, v in sorted(values.items(), key=lambda kv: -kv[1])[:n]]


def hbars(row, col, title, names, series_):
    return {"row": row, "col": col, "title": [title], "cats": names, "date": False, "horizontal": True, "series": series_,
            "tall": len(series_) > 2, "axes": [{"min": 0, "max": None, "fmt": "General"}]}


def detail_charts(D):
    """Graficos da abertura. Valores em milhares, como os do topo da pagina."""
    k = lambda v: None if v is None else v / 1000
    bar = lambda name, data, color, show=True: {
        "name": name, "type": "bar", "data": data, "color": color, "fill": color, "dash": None, "width": None, "noline": True,
        "marker": None, "markerColor": None, "show": show, "labels": [], "fmt": "0.0", "yAxis": 0}
    out = []
    Y = D["industry_ytd"]
    cols, rows = Y["cols"], Y["rows"]
    month = Y["month"]
    label = lambda m: bd.month_label(m)
    names = top({n: v[cols.index(month)] for n, v in rows.items()}, 10)
    out.append(hbars(25, 1, "Job Cuts by Industry", names,
                     [bar(label(c), [k(D["industry"][n].get(c)) for n in names], color)
                      for c, color in zip(reversed([c for c in cols if not c.startswith("YTD")]), ["156082", "A6CAEC", "BFBFBF"])]))
    ytd = [c for c in cols if c.startswith("YTD")]
    if len(ytd) == 2:
        cur, old = sorted(ytd, reverse=True)
        names = top({n: v[cols.index(cur)] for n, v in rows.items()}, 10)
        out.append(hbars(45, 1, "Job Cuts by Industry - YTD", names,
                         [bar(cur[3:], [k(rows[n][cols.index(cur)]) for n in names], "156082"),
                          bar(old[3:], [k(rows[n][cols.index(old)]) for n in names], "A6CAEC")]))
        leaders = top({n: v[cols.index(cur)] for n, v in rows.items()}, 5)
    else:
        leaders = names[:5]
    months = sorted({m for s in D["industry"].values() for m in s})
    palette = ["153D64", "156082", "6BA5D9", "A6CAEC", "3B7D23"]
    stacked = []
    for n, color in zip(leaders, palette):
        b = bar(n, [k(D["industry"][n].get(m, 0)) for m in months], color, show=False)
        b["stack"] = "total"
        stacked.append(b)
    others = bar("Others", [k(sum(s.get(m, 0) for n, s in D["industry"].items() if n not in leaders)) for m in months], "BFBFBF", show=False)
    others["stack"] = "total"
    stacked.append(others)
    out.append({"row": 65, "col": 1, "title": ["Job Cuts by Industry", "(Top 5 YTD and others)"], "cats": [label(m) for m in months],
                "date": True, "horizontal": False, "series": stacked, "axes": [{"min": 0, "max": None, "fmt": "0"}]})
    R = D["reason_ytd"]
    i_m, i_y = R["cols"].index(R["month"]), next(i for i, c in enumerate(R["cols"]) if c.startswith("YTD"))
    names = top({n: v[i_m] for n, v in R["rows"].items()}, 10)
    out.append(hbars(85, 1, f"Job Cuts by Reason - {label(R['month'])}", names, [bar(None, [k(R["rows"][n][i_m]) for n in names], "156082")]))
    names = top({n: v[i_y] for n, v in R["rows"].items()}, 10)
    out.append(hbars(85, 7, f"Job Cuts by Reason - {R['cols'][i_y][3:]} YTD", names, [bar(None, [k(R["rows"][n][i_y]) for n in names], "156082")]))
    rm = sorted({m for s in D["reason"].values() for m in s})
    pair = [("Artificial Intelligence", "C00000"), ("Market/Economic Conditions", "153D64")]
    out.append({"row": 105, "col": 1, "title": ["Job Cuts by Reason: Artificial Intelligence vs. Market/Economic Conditions"],
                "cats": [label(m) for m in rm], "date": True, "horizontal": False,
                "series": [line(n, [k(D["reason"].get(n, {}).get(m, 0)) for m in rm], c, marker=True,
                                labels=[{"i": len(rm) - 1, "fmt": "0.0", "fill": None}]) for n, c in pair],
                "axes": [{"min": None, "max": None, "fmt": "0"}]})
    H = D["hiring_ytd"]
    ytd = [c for c in H["cols"] if c.startswith("YTD")]
    if len(ytd) == 2:
        cur, old = sorted(ytd, reverse=True)
        i_c, i_o = H["cols"].index(cur), H["cols"].index(old)
        names = top({n: v[i_c] for n, v in H["rows"].items()}, 10)
        out.append(hbars(125, 1, "Hiring Offers by Industry - YTD", names,
                         [bar(cur[3:], [k(H["rows"][n][i_c]) for n in names], "156082"),
                          bar(old[3:], [k(H["rows"][n][i_o]) for n in names], "A6CAEC")]))
    return out


def render(data, published=None):
    as_of = max(m for m, r in data.items() if r.get("cuts") is not None)
    published = published or dt.datetime.now(BRT)
    payload = charts(data, as_of)
    try:
        payload += detail_charts(detail.load())
    except Exception as e:  # a abertura nunca atrapalha o headline
        print("abertura ficou de fora:", type(e).__name__, e)
    page = bd.fill_template("Challenger Job Cuts", "challenger", "state_challenger.json", "", "", as_of, published, payload)
    (ROOT / "docs/challenger.html").write_text(page, encoding="utf-8")
    json.dump({"as_of": as_of, "published": published.isoformat(timespec="seconds"), "next_release": None},
              open(ROOT / "docs/state_challenger.json", "w"))
    return as_of


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
    print(kv)


def update_detail(month):
    """Atualiza setores e motivos com o PDF ja baixado. Se nao fechar, o headline sai mesmo assim."""
    try:
        D = detail.load()
        pages = detail.pages_from_pdf(LAST_PDF["blob"])
        for name, title in (("industry", r"JOB CUTS BY INDUSTRY"), ("reason", r"JOB CUTS BY REASON"), ("hiring", r"HIRING PLANS")):
            try:
                detail.merge(D, {name: detail.table(pages, title)}, month)
            except Exception as e:
                print(f"tabela {name} ficou de fora:", e)
        detail.save(D)
    except Exception as e:
        print("abertura nao atualizada:", type(e).__name__, e)


def publish(data, month, rec, first_seen=None):
    data[month] = rec
    json.dump(dict(sorted(data.items())), open(DATA, "w"), separators=(",", ":"))
    update_detail(month)
    render(data)
    if first_seen:
        with open(ROOT / "data/log_challenger.jsonl", "a") as f:
            f.write(json.dumps({"as_of": month, "first_seen": first_seen.isoformat(timespec="seconds"),
                                "built": dt.datetime.now(BRT).isoformat(timespec="seconds")}) + "\n")
    output(changed="true", as_of=month)


def once():
    data = load()
    month, rec = latest_report()
    if data.get(month) == rec and "--force" not in sys.argv:
        print("Sem novidade.")
        output(changed="false")
        return 0
    publish(data, month, rec)
    return 0


def watch():
    now = dt.datetime.now(ET)
    data = load()
    expected = calc.shift(now.date().isoformat()[:7], -1)
    have = max(data)
    if have >= expected or now.day > 12:
        print("Nada a esperar hoje.")
        output(changed="false")
        return 0
    if now.time() >= STOP:
        return once()
    if now.time() < dt.time(5, 15):
        print("Cedo demais; a proxima rodada assume.")
        output(changed="false")
        return 0
    start = now.replace(hour=START.hour, minute=START.minute, second=START.second, microsecond=0)
    if now < start:
        time.sleep((start - now).total_seconds())
    while dt.datetime.now(ET).time() < STOP:
        try:
            month, rec = latest_report(expected)
            if month >= expected:
                first_seen = dt.datetime.now(BRT)
                publish(data, month, rec, first_seen)
                return 0
        except Exception as e:
            print("aguardando:", type(e).__name__, e)
        t = dt.datetime.now(ET).time()
        time.sleep(10 if t < dt.time(7, 45) else 30)
    print("Relatorio nao apareceu ate", STOP)
    output(changed="false")
    return 0


if __name__ == "__main__":
    sys.exit(watch() if "--watch" in sys.argv else once())
