"""Pagina do JOLTS: mesmas contas da aba Graficos do JOLTS.xlsx.

A linha 4 da grade e o mes mais recente, como no Excel. As letras de entrada sao as da aba BBG.
"""
import datetime as dt, html, json, os, pathlib, sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build_dashboard as bd, calc, fetch_bls

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERIES = {"B": "JTS000000000000000HIL", "C": "CES0000000001", "D": "JTS000000000000000LDL",
          "E": "JTS000000000000000JOL", "F": "JTS000000000000000QUL", "G": "JTS000000000000000JOL",
          "H": "LNS13000000", "I": "LNS11000000"}
LAST = 184
NEXT_RELEASE = "2026-12-01T10:00:00-05:00"


def fetch(key):
    ids = sorted(set(SERIES.values()))
    year = dt.datetime.now(dt.timezone.utc).year
    raw = {}
    out = fetch_bls.post(ids, 2000, min(2019, year), key), fetch_bls.post(ids, 2020, year, key)
    for o in out:
        for s in o["Results"]["series"]:
            pts = raw.setdefault(s["seriesID"], {})
            for p in s["data"]:
                if p["period"].startswith("M") and p["period"] != "M13":
                    try:
                        pts[f'{p["year"]}-{p["period"][1:]}'] = float(p["value"])
                    except ValueError:
                        pts[f'{p["year"]}-{p["period"][1:]}'] = None
    return {k: dict(sorted(v.items())) for k, v in raw.items()}


def levels(raw):
    return {c: raw[i] for c, i in SERIES.items()}


def latest_month(L):
    return calc.latest_month(L, list(SERIES))


def rates(L, m):
    v = lambda c: L[c].get(m)
    q = lambda a, b: None if a is None or b in (None, 0) else a / b
    vac = None if v("E") is None or v("C") is None else v("E") / (v("E") + v("C"))
    return {"B": vac, "C": q(v("H"), v("I")), "D": q(v("B"), v("C")), "E": q(v("D"), v("C")), "F": vac,
            "G": q(v("F"), v("C")), "L": q(v("G"), v("H"))}


def build_grid(L, as_of):
    G = {}
    def setc(c, r, x):
        G.setdefault(c, {})[r] = x
    for r in range(4, LAST + 1):
        m = calc.shift(as_of, 4 - r)
        setc("A", r, m)
        for c, x in rates(L, m).items():
            setc(c, r, x)
    for gc, src in [("H", "D"), ("I", "E"), ("J", "F"), ("K", "G"), ("M", "L")]:
        a = calc.avg([G[src][r] for r in range(4, LAST + 1) if G["A"][r][:4] == "2019"])
        for r in range(4, LAST + 1):
            setc(gc, r, a)
    return G


def table(G, L, as_of):
    months = [calc.shift(as_of, -12), calc.shift(as_of, -2), calc.shift(as_of, -1), as_of]
    row = lambda m: 4 + (int(as_of[:4]) * 12 + int(as_of[5:]) - int(m[:4]) * 12 - int(m[5:]))
    jo = calc.avg([x for m, x in L["E"].items() if m[:4] == "2019"])
    items = [("Job openings", None, jo, "{:.0f}"), ("V/U", "L", G["M"][4], "{:.2f}"), ("Hiring rate", "D", G["H"][4], "{:.1%}"),
             ("Layoff rate", "E", G["I"][4], "{:.1%}"), ("Vacancy rate", "F", G["J"][4], "{:.1%}"),
             ("Quits rate", "G", G["K"][4], "{:.1%}")]
    rows = []
    for name, col, base, f in items:
        vals = [L["G"].get(m) if col is None else G[col].get(row(m)) for m in months]
        tds = "".join(f"<td>{'' if v is None else f.format(v)}</td>" for v in vals)
        rows.append(f"<tr><td>{name}</td>{tds}<td>{f.format(base)}</td></tr>")
    head = "".join(f"<th>{bd.month_label(m)}</th>" for m in months)
    return ('<table class="t1 plain"><thead><tr><th></th>' + head + "<th>2019 Avg.</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def beveridge(L, as_of):
    start = "2000-12"
    groups = [("2000-2008", start, "2008-12", "153D64"), ("2009-2019", "2009-01", "2019-12", "7F7F7F"),
              ("2020-2024", "2020-01", "2024-12", "196B24"), (f"2025-{as_of[:4]}", "2025-01", as_of, "F4B183")]
    series = []
    def pt(m):
        r = rates(L, m)
        return None if r["C"] is None or r["B"] is None else [r["C"], r["B"], bd.month_label(m)]
    months = sorted(L["E"])
    for name, a, b, col in groups:
        pts = [pt(m) for m in months if a <= m <= b and m <= as_of]
        series.append({"name": name, "color": col, "points": [p for p in pts if p]})
    for m, col in [(calc.shift(as_of, -12), "92D050"), (calc.shift(as_of, -1), "FFFF00"), (as_of, "FF0000")]:
        series.append({"name": bd.month_label(m), "color": col, "points": [p for p in [pt(m)] if p], "z": 6})
    return {"row": 14, "col": 1, "title": ["Beveridge Curve"], "scatter": True, "series": series, "tall": True,
            "xMin": 0.02, "xMax": 0.16, "cats": [], "date": False, "horizontal": False,
            "axes": [{"min": 0, "max": None, "fmt": "0%"}],
            "arrows": [{"from": [0.12, 0.074], "to": [0.12, 0.046], "color": "#153D64", "text": "Soft Landing", "side": "left"},
                       {"from": [0.12, 0.074], "to": [0.13, 0.064], "color": "#0F9ED5", "text": "Hard Landing", "side": "right"}]}


def line_charts(G):
    spec = json.load(open(ROOT / "scripts/jolts_charts.json"))
    out = []
    for ch in spec:
        if not ch["series"]:
            continue
        title = [t for t in ch["title"] if t]
        val = next(a for a in ch["axes"].values() if a["kind"] == "valAx")
        date_min = next((a["min"] for a in ch["axes"].values() if a["kind"] == "dateAx" and a["min"]), None)
        cats = [G["A"][r] for r in range(LAST, 3, -1)]
        k = 0
        if date_min:
            start = bd.serial_to_ym(date_min)
            k = next(j for j, m in enumerate(cats) if m >= start)
        series = []
        for s in ch["series"]:
            col = bd.cells(s["val"])[0][0]
            data = [G[col][r] for r in range(LAST, 3, -1)][k:]
            color = {"accent2/75000": "C04F15", "accent3": "196B24"}.get(s["color"], s["color"])
            fmt = "0.00" if col in ("L", "M") else "0.0%"
            labels = [dict(l, i=len(data) - 1) for l in s["labels"]]
            series.append({"name": None if col not in ("M", "H", "I", "J", "K") else None, "type": "line", "data": data,
                           "color": color, "fill": None, "dash": s["dash"], "width": s["width"], "noline": False,
                           "marker": ["none", None], "markerColor": None, "show": False, "labels": labels,
                           "fmt": fmt, "yAxis": 0})
        out.append({"row": ch["row"], "col": 1, "title": title, "cats": [bd.month_label(m) for m in cats[k:]], "date": True,
                    "horizontal": False, "series": series, "axes": [{"min": val["min"], "max": val["max"], "fmt": val["fmt"]}]})
    return out


def validate(L, as_of):
    errs = []
    for c in SERIES:
        if L[c].get(as_of) is None:
            errs.append(f"{c} sem {as_of}")
    if not errs:
        v = rates(L, as_of)
        if not 0.01 < v["B"] < 0.12:
            errs.append("Vacancy rate fora do normal")
        if not 0.1 < v["L"] < 4:
            errs.append("V/U fora do normal")
    return errs


def render(raw, published=None):
    L = levels(raw)
    as_of = latest_month(L)
    errs = validate(L, as_of)
    if errs:
        raise SystemExit("JOLTS nao publicado: " + "; ".join(errs))
    G = build_grid(L, as_of)
    charts = [beveridge(L, as_of)] + line_charts(G)
    published = published or dt.datetime.now(ZoneInfo("America/Sao_Paulo"))
    state = {"as_of": as_of, "published": published.isoformat(timespec="seconds"), "next_release": NEXT_RELEASE}
    page = bd.fill_template("JOLTS", "jolts", "state_jolts.json", table(G, L, as_of), "", as_of, published, charts)
    (ROOT / "docs/jolts.html").write_text(page, encoding="utf-8")
    json.dump(state, open(ROOT / "docs/state_jolts.json", "w"))
    return as_of


if __name__ == "__main__":
    raw = fetch(os.environ["BLS_API_KEY"])
    json.dump(raw, open(ROOT / "data/raw_jolts.json", "w"), separators=(",", ":"))
    print(render(raw))
