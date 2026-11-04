"""Reproduz as contas da aba Graficos do Household & Establishment Data.xlsx.

A saida e uma grade igual a aba: grid["DA"][8] e a coluna DA, linha 8.
A linha 7 e sempre o mes mais recente; a linha 8, o mes anterior, e assim por diante.
Os dados de entrada usam as letras da aba Bloomberg (L["AZ"]["2026-09"] = Unemployed).
"""
import json, pathlib, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAST_ROW = 187
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def shift(ym, k):
    y, m = int(ym[:4]), int(ym[5:])
    t = y * 12 + m - 1 + k
    return f"{t // 12}-{t % 12 + 1:02d}"


def avg(values):
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def sub(a, b):
    return None if a is None or b is None else a - b


def ratio(a, b):
    return None if a is None or b in (None, 0) else a / b


def percentile(values, p):
    v = sorted(values)
    if not v:
        return None
    i = (len(v) - 1) * p
    lo = int(i)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def levels_from_raw(raw):
    """Monta as colunas da aba Bloomberg a partir das series do BLS, sem preencher meses vazios."""
    series = json.load(open(ROOT / "scripts/series.json"))
    L = {col: dict(raw[s["id"]]) for col, s in series.items()}
    emp = raw["LNS12000000"]
    L["AX"] = {m: sub(emp.get(m), emp.get(shift(m, -1))) for m in emp}
    return L


def fill_like_bloomberg(L):
    """Repete o mes anterior quando nao ha dado, como o BDH da Bloomberg. So para validacao."""
    out = {}
    for col, s in L.items():
        ms = sorted(s)
        filled, last = {}, None
        for m in ms:
            last = s[m] if s[m] is not None else last
            filled[m] = last
        out[col] = filled
    return out


def latest_month(L, cols):
    """Ultimo mes em que todas as colunas pedidas tem valor."""
    return min(max(m for m, v in L[c].items() if v is not None) for c in cols)


def build_grid(L, as_of):
    G = {}
    rows = range(7, LAST_ROW + 1)

    def setc(col, r, v):
        G.setdefault(col, {})[r] = v

    def mon(r):
        return shift(as_of, 7 - r)

    def bb(c, r):
        return L[c].get(mon(r))

    for r in rows:
        setc("A", r, mon(r))
    def g(col, r):
        return G.get(col, {}).get(r)

    # Variacao mensal de emprego (Grafico <- Bloomberg)
    diffs = {c: c for c in "B C D E F G H I J K L M N O P Q R S T U V".split()}
    diffs.update({"Z": "W", "AA": "X", "AB": "Y", "AC": "AA"})
    for gc, bc in diffs.items():
        for r in rows:
            setc(gc, r, sub(bb(bc, r), bb(bc, r + 1)))
    names = {"E": "Mining and Logging", "F": "Construction", "G": "Manufacturing",
             "I": "Trade, Transportation, and Utilities", "J": "Information", "K": "Financial Activities",
             "L": "Professional And Business Services", "M": "Education and Health Services",
             "N": "Leisure and Hospitality", "O": "Other Services", "P": "Government",
             "Q": "Federal", "R": "State", "S": "Local"}
    for c, n in names.items():
        setc(c, 6, n)
    # Niveis/taxas copiados da aba Bloomberg
    copies = {"CN": "AR", "CO": "AS", "CT": "AW", "CU": "AX", "CV": "AY", "CY": "BC", "CZ": "BD",
              "DB": "BF", "DC": "BG", "DD": "BH", "DH": "BI", "DI": "BJ", "DJ": "BK", "DN": "BL",
              "DO": "BM", "DP": "BN", "DQ": "BO", "DS": "BP", "DT": "BQ", "DU": "BR", "DX": "BS",
              "DY": "BT", "DZ": "BU", "EB": "BX", "EC": "BY", "EE": "CA", "EF": "CB", "EG": "CC",
              "EH": "CD"}
    for gc, bc in copies.items():
        for r in rows:
            setc(gc, r, bb(bc, r))
    for r in rows:
        setc("AE", r, None if None in (g("B", r), g("P", r), g("Z", r)) else g("B", r) - g("P", r) - g("Z", r))
        parts = [g(c, r) for c in ("F", "G", "AC", "AA", "L", "N", "O")]
        setc("AH", r, None if None in parts else sum(parts))
        setc("AI", r, sub(g("B", r), g("AH", r)))
        setc("DV", r, None if None in (g("DN", r), g("DO", r)) else g("DN", r) + g("DO", r))
        setc("DE", r, None if g("DD", r) is None else g("DD", r) / 100)
        setc("DA", r, ratio(bb("AZ", r), bb("AV", r)))
        # Salarios
        setc("BN", r, None if ratio(bb("BW", r), bb("BW", r + 1)) is None else ratio(bb("BW", r), bb("BW", r + 1)) ** 12 - 1)
        for gc, bc, base in [("BO", "BW", 12), ("BR", "AD", 12), ("BQ", "AD", 1), ("BT", "AE", 1),
                             ("CB", "AF", 1), ("CC", "AG", 1), ("CD", "AH", 1), ("CE", "AI", 1),
                             ("CF", "AJ", 1), ("CG", "AK", 1), ("CH", "AL", 1), ("CI", "AM", 1),
                             ("CJ", "AN", 1), ("CK", "AO", 1), ("CL", "AP", 1), ("CM", "AQ", 1)]:
            q = ratio(bb(bc, r), bb(bc, r + base))
            setc(gc, r, None if q is None else q - 1)
        a = avg([bb("AD", r + i) for i in range(6)])
        b = avg([bb("AD", r + i) for i in [6, 1, 2, 3, 4, 5]])
        q = ratio(a, b)
        setc("BS", r, None if q is None else q ** 12 - 1)
        setc("BU", r, avg([bb("AE", r + i) for i in range(6)]))
    for r in rows:
        q = ratio(g("BU", r), avg([bb("AE", r + 1 + i) for i in range(6)]))
        setc("BV", r, None if q is None else q - 1)
    # U rate com participacao fixa em dez/25 e U rate sem temporary layoff
    lfpr = L["AW"].get("2025-12")
    for r in rows:
        pop, clf, un, tmp = bb("AU", r), bb("AV", r), bb("AZ", r), bb("BB", r)
        if None in (pop, clf, un) or lfpr is None:
            setc("DK", r, None)
        else:
            setc("DK", r, (pop * lfpr / 100 - clf + un) / (pop * lfpr / 100))
        setc("DL", r, None if None in (un, tmp, clf) else (un - tmp) / clf)
    # Medias moveis de 3 meses
    for gc, src in {"W": "B", "X": "C", "Y": "P", "AD": "Z", "AF": "AE", "AJ": "AH", "AK": "AI",
                    "DR": "DQ", "DW": "DV"}.items():
        for r in rows:
            setc(gc, r, avg([g(src, r + i) for i in range(3)]))
    # Medias 2016-2019
    def in_base(m):
        return "2016-01" <= m <= "2019-12"
    def base_avg(col, last_row):
        return avg([g(col, r) for r in range(7, last_row + 1) if in_base(mon(r))])
    for gc, src, last in [("AL", "AJ", 171), ("AM", "AK", 171), ("CW", "CV", 171),
                          ("DF", "DE", 175), ("DG", "DA", 175)]:
        v = base_avg(src, last)
        for r in rows:
            setc(gc, r, v)
    for gc, bc in [("CP", "AR"), ("CQ", "AS")]:
        v = avg([x for m, x in L[bc].items() if in_base(m)])
        for r in rows:
            setc(gc, r, v)
    yoy = []
    for m, x in L["BW"].items():
        if in_base(m) and L["BW"].get(shift(m, -12)):
            yoy.append(x / L["BW"][shift(m, -12)] - 1)
    for r in rows:
        setc("BP", r, avg(yoy))
    # Faixas fixas de salario dos anos 70 e 10 (valores digitados no Excel)
    fixed = {"BW": 0.005690235084338028, "BX": 0.006333378888138064, "BY": 0.004958828036994989,
             "BZ": 0.001965806022923873, "CA": 0.0013745508511430748}
    for gc, v in fixed.items():
        for r in range(7, 93):
            setc(gc, r, v)
    # NSA por mes
    t = L["T"]
    y1 = int(as_of[:4])
    for i, name in enumerate(MONTHS):
        r = 7 + i
        mm = i + 1
        setc("AR", r, name)
        setc("AS", r, mm)
        vals = []
        for m, x in t.items():
            if int(m[5:]) == mm and x is not None:
                prev = t.get(shift(m, -1))
                # A formula do Excel filtra pela data do mes anterior a variacao
                if prev is not None and "2015-01" <= shift(m, -1) <= "2019-12":
                    vals.append(x - prev)
        setc("AT", r, statistics.median(vals) if vals else None)
        def nsa(y):
            m = f"{y}-{mm:02d}"
            return g("T", 7 + (int(as_of[:4]) * 12 + int(as_of[5:]) - y * 12 - mm)) if m <= as_of else None
        setc("AU", r, nsa(y1 - 1))
        setc("AV", r, nsa(y1))
    setc("AU", 6, y1 - 1)
    setc("AV", 6, y1)
    m0 = int(as_of[5:])
    setc("AT", 20, m0)
    setc("AV", 20, MONTHS[m0 - 1])
    setc("AU", 20, "Nonfarm Payroll Increase NSA - " + MONTHS[m0 - 1])
    base = []
    for i, y in enumerate(range(y1 - 15, y1 + 1)):
        r = 22 + i
        setc("AS", r, y)
        v = sub(t.get(f"{y}-{m0:02d}"), t.get(shift(f"{y}-{m0:02d}", -1)))
        setc("AT", r, v)
        if y in (2016, 2017, 2018, 2019):
            base.append(v)
    for i, y in enumerate(range(y1 - 15, y1 + 1)):
        setc("AU", 22 + i, avg(base) if y in (2016, 2017, 2018, 2019) else None)
    # Setores por trimestre
    sectors = {"AZ": "E", "BA": "F", "BB": "G", "BC": "I", "BD": "J", "BE": "K", "BF": "L", "BG": "M",
               "BH": "N", "BI": "O", "BJ": "P"}
    def quarter(m):
        return f"{(int(m[5:]) - 1) // 3 + 1}Q{m[:4]}"
    labels = []
    for r in range(7, 22):
        q = quarter(mon(r))
        setc("AY", r, q)
        if q not in labels:
            labels.append(q)
    for i, q in enumerate(labels[:5]):
        setc("AY", 25 + i, q)
    setc("AY", 31, "Average 2016-2019")
    for gc, bc in sectors.items():
        setc(gc, 6, names[bc])
        for r in range(7, 22):
            setc(gc, r, g(bc, r))
        for i, q in enumerate(labels[:5]):
            setc(gc, 25 + i, avg([g(gc, r) for r in range(7, 22) if g("AY", r) == q]))
        s = L[bc]
        setc(gc, 31, avg([sub(x, s.get(shift(m, -1))) for m, x in s.items() if in_base(m)]))
    # Comparacao por mes contra p20, mediana e p80 de 2012-2019
    blocks = [(8, "EV", "B"), (8, "FD", "C"), (8, "FL", "E"), (8, "FT", "F"), (8, "GB", "G"),
              (22, "EV", "I"), (22, "FD", "J"), (22, "FL", "K"), (22, "FT", "L"), (22, "GB", "M"),
              (36, "EV", "N"), (36, "FD", "O"), (36, "FL", "P"), (36, "FT", "Z")]
    from_col = lambda c: sum((ord(x) - 64) * 26 ** i for i, x in enumerate(reversed(c)))
    to_col = lambda n: (to_col((n - 1) // 26) if n > 26 else "") + chr((n - 1) % 26 + 65)
    window = [r for r in range(7, 176)]
    for start, first, src in blocks:
        c0 = from_col(first)
        for j, name in enumerate(["y2", "y1", "y0", "p20", "med", "p80"]):
            col = to_col(c0 + j)
            setc(col, 7, {"y2": y1 - 2, "y1": y1 - 1, "y0": y1, "p20": "p20", "med": "med", "p80": "p80"}[name])
            for i in range(12):
                mm = i + 1
                r = start + i
                setc("ET", r, MONTHS[i])
                if name in ("y2", "y1", "y0"):
                    y = {"y2": y1 - 2, "y1": y1 - 1, "y0": y1}[name]
                    d = int(as_of[:4]) * 12 + int(as_of[5:]) - y * 12 - mm
                    setc(col, r, g(src, 7 + d) if d >= 0 else None)
                else:
                    p = {"p20": .2, "med": .5, "p80": .8}[name]
                    vals = [g(src, q) for q in window if int(mon(q)[5:]) == mm
                            and 2012 <= int(mon(q)[:4]) <= 2019 and g(src, q) is not None]
                    setc(col, r, percentile(vals, p))
    return G
