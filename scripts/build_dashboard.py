"""Gera docs/index.html com os mesmos graficos e tabelas do PDF do Employment Tracker."""
import datetime as dt, html, json, pathlib, re, sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import calc

ROOT = pathlib.Path(__file__).resolve().parent.parent
MON = calc.MONTHS
REQUIRED = ["B", "C", "E", "F", "G", "I", "J", "K", "L", "M", "N", "O", "P", "T", "W", "X", "AA",
            "AD", "AE", "AR", "AS", "AU", "AV", "AW", "AY", "AZ", "BB", "BC", "BD", "BF", "BG", "BH",
            "BI", "BJ", "BK", "BL", "BM", "BO", "BW", "BX", "BY", "CA", "CB", "CC", "CD"]
LABEL_FMT = {"DA": "0.00%", "DE": "0.0%", "DG": "0.0%", "DF": "0.0%", "DK": "0.00%", "DL": "0.00%",
             "BN": "0.0%", "BR": "0.00%", "BS": "0.00%", "BT": "0.00%", "BV": "0.00%",
             "CN": "0.0", "CO": "0.0", "CP": "0.0", "CQ": "0.0", "CT": "0.0", "CV": "0.0", "CW": "0.0"}


def month_label(ym):
    return f"{MON[int(ym[5:]) - 1]}-{ym[2:4]}"


def cells(ref):
    out = []
    for sheet_ref in ref.strip("()").split(","):
        m = re.match(r".*!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", sheet_ref)
        c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3) or m.group(1), int(m.group(4) or m.group(2))
        num = lambda c: sum((ord(x) - 64) * 26 ** i for i, x in enumerate(reversed(c)))
        col = lambda n: (col((n - 1) // 26) if n > 26 else "") + chr((n - 1) % 26 + 65)
        for cn in range(num(c1), num(c2) + 1):
            for r in range(r1, r2 + 1):
                out.append((col(cn), r))
    return out


def serial_to_ym(x):
    d = dt.date(1899, 12, 30) + dt.timedelta(days=int(x))
    return f"{d.year}-{d.month:02d}"


def charts_payload(G):
    spec = json.load(open(ROOT / "scripts/charts.json"))
    get = lambda c, r: G.get(c, {}).get(r)
    payload = []
    for ch in spec:
        title = [t for t in ch["title"] if t] if isinstance(ch["title"], list) else []
        if title and title[0].startswith("="):
            c, r = cells(title[0])[0]
            title = [get(c, r)]
        date_axis = any(a["kind"] == "dateAx" for a in ch["axes"].values())
        vals = [a for a in ch["axes"].values() if a["kind"] == "valAx"]
        date_min = next((a["min"] for a in ch["axes"].values() if a["kind"] == "dateAx" and a["min"]), None)
        cats = None
        series = []
        for i, s in enumerate(ch["series"]):
            refs = cells(s["val"])
            data = [get(c, r) for c, r in refs]
            cat = [get(c, r) for c, r in cells(s["cat"])] if s["cat"] else None
            if cat and cat[0] is None and s["cat"]:  # cabecalho de setores
                cat = [get(c, 6) for c, r in cells(s["cat"])]
            if date_axis:
                data = data[::-1]
                cat = cat[::-1] if cat else None
            if cat and cats is None:
                cats = cat
            name = s["name"]
            if s["nameRef"]:
                c, r = cells(s["nameRef"])[0]
                name = get(c, r)
            if refs[0][0] == "AV" and refs[0][1] == 7:
                name = str(G["AV"][6])
            if refs[0][0] == "AU" and refs[0][1] == 7:
                name = str(G["AU"][6])
            name = None if name is None else str(name)
            if name in ("U rate with Stable Labor Force Participation", "U rate Ex-Temporary Layoff"):
                name = None
            colr = refs[0][0]
            fmt = LABEL_FMT.get(colr) or s["labelFmt"]
            ax = next((a for k, a in ch["axes"].items() if k in s["ax"] and a["kind"] == "valAx"), vals[0])
            series.append({"name": name, "type": s["type"], "data": data, "color": s["color"], "fill": s["fill"],
                           "dash": s["dash"], "width": s["width"], "noline": s["noline"], "marker": s["marker"],
                           "markerColor": s["markerColor"], "show": s["show"], "labels": s["labels"], "fmt": fmt,
                           "yAxis": 1 if ax["pos"] == "r" else 0})
        if date_axis and date_min:
            start = serial_to_ym(date_min)
            k = next((j for j, m in enumerate(cats) if m >= start), 0)
            for s in series:
                s["data"] = s["data"][k:]
                s["labels"] = [dict(l, i=l["i"] - k) for l in s["labels"] if l["i"] >= k]
            cats = cats[k:]
        if date_axis:
            cats = [month_label(m) for m in cats]
        payload.append({"row": ch["row"], "col": ch["col"], "title": title, "cats": cats, "date": date_axis,
                        "horizontal": ch["dir"] == "bar", "series": series,
                        "axes": [{"min": a["min"], "max": a["max"], "fmt": a["fmt"]}
                                 for a in sorted(vals, key=lambda a: a["pos"] == "r")]})
    return payload


def table_summary(G, L, as_of):
    idx = {"Sep-25": 19, "m2": 9, "m1": 8, "m0": 7}
    months = [calc.shift(as_of, -12), calc.shift(as_of, -2), calc.shift(as_of, -1), as_of]
    def val(col, m, mult=1):
        s = G[col]
        r = 7 + (int(as_of[:4]) * 12 + int(as_of[5:]) - int(m[:4]) * 12 - int(m[5:]))
        v = s.get(r)
        return None if v is None else v * mult
    groups = [("Employment status", [("Participation Rate", "CT", 1, 1), ("Unemployment rate", "DA", 100, 2),
                                     ("Employment-population ratio", "CV", 1, 1)]),
              ("Unemployment rates", [("U1 - Unemployed 15 weeks or longer", "CY", 1, 1),
                                      ("U2 - Job losers & completed temporary jobs", "CZ", 1, 1),
                                      ("U4 - Unemployed + discouraged workers", "DB", 1, 1),
                                      ("U5 - Unemployed, discouraged, marginally attached", "DC", 1, 1),
                                      ("U6 - Unemployed, marginally attached, part-time", "DD", 1, 1)]),
              ("Age", [("16-24", "DH", 1, 1), ("25-54", "DI", 1, 1), ("55+", "DJ", 1, 1)])]
    head = "".join(f"<th>{month_label(m)}</th>" for m in months)
    rows = []
    for g, items in groups:
        rows.append(f'<tr class="grp"><td>{g}</td><td></td><td></td><td></td><td></td><td></td></tr>')
        for name, col, mult, dec in items:
            vs = [val(col, m, mult) for m in months]
            base = val(col, "2020-02", mult)
            delta = None if vs[-1] is None or base is None else vs[-1] - base
            tds = "".join(f"<td{' class=hi' if col == 'DA' and j == 3 else ''}>{'' if v is None else f'{v:.{dec}f}'}</td>"
                          for j, v in enumerate(vs))
            ddec = 2 if col == "DA" else 1
            rows.append(f"<tr><td>{html.escape(name)}</td>{tds}<td>{'' if delta is None else f'{delta:.{ddec}f}'}</td></tr>")
    return f'<table class="t1"><thead><tr><th></th>{head}<th>Today - Feb 2020</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'


def table_wages(G, L, as_of):
    names = [("All Employees", "AD", "BQ"), ("Production and Nonsupervisory Workers", "AE", "BT"),
             ("Goods-producing sector", "AF", "CB"), ("Mining and Logging", "AG", "CC"),
             ("Construction", "AH", "CD"), ("Manufacturing", "AI", "CE"), ("Private Service-Providing", "AJ", "CF"),
             ("Trade, Transportation, and Utilities", "AK", "CG"), ("Information", "AL", "CH"),
             ("Financial Activities", "AM", "CI"), ("Professional And Business Services", "AN", "CJ"),
             ("Education and Health Services", "AO", "CK"), ("Leisure and Hospitality", "AP", "CL"),
             ("Other Services", "AQ", "CM")]
    months = [calc.shift(as_of, -2), calc.shift(as_of, -1), as_of]
    rows = []
    for n, lc, gc in names:
        tds = "".join(f"<td>{G[gc][9 - i] * 100:.2f}%</td>" for i in range(3))
        rows.append(f"<tr><td>{n}</td><td>${L[lc][as_of]:.2f}</td>{tds}</tr>")
    hd = "".join(f"<th>{month_label(m)}</th>" for m in months)
    return ('<table class="t2"><thead><tr class="sup"><th></th><th></th><th colspan="3">MoM Growth of Wages</th></tr>'
            f'<tr><th>Sector</th><th>{month_label(as_of)}</th>{hd}</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def fill_template(title, page_id, state_file, table1, table2, as_of, published, payload):
    tpl = (ROOT / "scripts/template.html").read_text(encoding="utf-8")
    table2_html = f'<div class="tw" data-title="MoM Growth of Wages">{table2}</div>' if table2 else ""
    return (tpl.replace("__TITLE__", title).replace("__PAGE__", page_id).replace("__STATE__", state_file)
            .replace("__TABLE1__", table1).replace("__TABLE2BLOCK__", table2_html)
            .replace("__ASOF__", month_label(as_of)).replace("__ASOFKEY__", as_of)
            .replace("__PUBLISHED__", published.strftime("%d/%m/%Y %H:%M"))
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))))


def render(raw, as_of=None, published=None, out=ROOT / "docs/index.html"):
    L = calc.levels_from_raw(raw)
    as_of = as_of or calc.latest_month(L, REQUIRED)
    G = calc.build_grid(L, as_of)
    payload = charts_payload(G)
    published = published or dt.datetime.now(ZoneInfo("America/Sao_Paulo"))
    page = fill_template("Employment Situation Summary", "es", "state.json", table_summary(G, L, as_of),
                         table_wages(G, L, as_of), as_of, published, payload)
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return as_of


if __name__ == "__main__":
    raw = json.load(open(ROOT / "data/raw.json"))
    print(render(raw))
