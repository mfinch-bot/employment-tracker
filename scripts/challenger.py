"""Pagina do Challenger: le o relatorio mensal direto do site da Challenger, Gray & Christmas.

Modos:
  --watch  consulta o site a partir de 7:29:30 ET; nunca publica antes de 7:30 ET
  --once   confere uma vez e publica se houver mes novo
"""
import datetime as dt, html, io, json, os, pathlib, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build_dashboard as bd, calc

ROOT = pathlib.Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
BRT = ZoneInfo("America/Sao_Paulo")
POSTS = "https://www.challengergray.com/wp-json/wp/v2/posts?categories=61&per_page=2&_fields=date_gmt,link,title,content"
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
OFFICIAL = dt.time(7, 30)
START = dt.time(7, 29, 30)
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
    h = re.search(r"plans to hire ([\d,]+) workers in ([A-Z][a-z]+)", plain)
    if not m or not h:
        raise ValueError("texto do relatorio fora do padrao")
    cuts_post, month = num(m.group(1)), m.group(2)
    hire_post = num(h.group(1))
    if month not in MONTH_NAMES or h.group(2) != month:
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
    hires = [num(a) for a, b, c in re.findall(r"(?m)^TOTAL\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", pdf_text)]
    if hire_post not in hires:
        raise ValueError(f"contratacoes nao batem: {hire_post} x {hires}")
    return month, cuts, hire_post, gov_m


def pdf_text(url):
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(get(url))).pages)


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


def render(data, published=None):
    as_of = max(m for m, r in data.items() if r.get("cuts") is not None)
    published = published or dt.datetime.now(BRT)
    page = bd.fill_template("Challenger Job Cuts", "challenger", "state_challenger.json", "", "", as_of, published, charts(data, as_of))
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


def publish(data, month, rec, first_seen=None):
    data[month] = rec
    json.dump(dict(sorted(data.items())), open(DATA, "w"), separators=(",", ":"))
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
    if now.time() < dt.time(6, 45):
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
                while dt.datetime.now(ET).time() < OFFICIAL:
                    time.sleep(1)
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
