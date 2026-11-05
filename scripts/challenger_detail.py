"""Abertura do relatorio da Challenger: tabelas 2 (setores), 4 (motivos) e 7 (hiring por setor).

Le a posicao das palavras no PDF, porque celula vazia (zero) nao aparece no texto.
Cada tabela so vale se a soma das linhas fechar com o TOTAL em todas as colunas.
"""
import io, json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data/challenger_detail.json"
MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def lines(words):
    rows, cur, last = [], [], None
    for w in sorted(words, key=lambda w: w[2]):
        if last is not None and w[2] - last > 3:
            rows.append(sorted(cur))
            cur = []
        cur.append(w)
        last = w[2]
    if cur:
        rows.append(sorted(cur))
    return rows


def month_key(text):
    t = text.upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z]{3})-?(\d\d)", t)
    if m and m.group(1) in MON:
        return f"20{m.group(2)}-{MON[m.group(1)]:02d}"
    m = re.fullmatch(r"(\d\d)-?([A-Z]{3})", t)
    if m and m.group(2) in MON:
        return f"20{m.group(1)}-{MON[m.group(2)]:02d}"
    return None


def columns(row):
    """Colunas do cabecalho: [(borda direita, chave)], onde chave e AAAA-MM ou YTDAAAA."""
    w = row[1:]
    cols, i = [], 0
    while i < len(w):
        t = w[i][3]
        if t.upper() in ("YTD", "FULL", "YEAR"):
            i += 1
        elif re.fullmatch(r"20\d\d", t):
            cols.append((w[i][1], "YTD" + t))
            i += 1
        elif i + 2 < len(w) and w[i + 1][3] == "-":
            cols.append((w[i + 2][1], month_key(t + w[i + 2][3])))
            i += 3
        else:
            cols.append((w[i][1], month_key(t)))
            i += 1
    return cols


def clean_name(name):
    return re.sub(r"\s+\d$", "", re.sub(r"\s+", " ", name)).strip()


def table(pages, title):
    """Procura o titulo e devolve {"cols": [...], "rows": {nome: [valores]}}. None se nao achar ou nao fechar."""
    for p in pages:
        rows = lines(p["words"])
        for i, r in enumerate(rows):
            if not re.search(title, " ".join(w[3] for w in r), re.I):
                continue
            head = next((j for j in range(i + 1, min(i + 4, len(rows)))
                         if rows[j][0][3].upper() in ("INDUSTRY", "REASON", "SECTOR")
                         or (len(rows[j]) >= 2 and month_key(rows[j][0][3]))), None)
            if head is None:
                continue
            first = rows[head]
            if month_key(first[0][3]):  # cabecalho sem o rotulo da primeira coluna
                first = [[0, 0, 0, "Industry"]] + first
            cols = columns(first)
            if not cols or None in [c[1] for c in cols]:
                raise ValueError(f"cabecalho nao reconhecido: {[w[3] for w in rows[head]]}")
            limit = min(c[0] for c in cols) - 75
            out = {}
            for row in rows[head + 1:]:
                nums = [w for w in row if re.fullmatch(r"[\d,]+", w[3]) and w[0] > limit]
                name = clean_name(" ".join(w[3] for w in row if w not in nums))
                if not name:
                    continue
                vals = [0] * len(cols)
                for w in nums:
                    k = min(range(len(cols)), key=lambda c: abs(cols[c][0] - w[1]))
                    vals[k] += int(w[3].replace(",", ""))
                out[name] = vals
                if name == "TOTAL":
                    break
            if "TOTAL" not in out:
                raise ValueError(f"tabela sem TOTAL: {title}")
            for k in range(len(cols)):
                soma = sum(v[k] for n, v in out.items() if n != "TOTAL")
                if soma != out["TOTAL"][k]:
                    raise ValueError(f"{title} nao fecha na coluna {cols[k][1]}: {soma} x {out['TOTAL'][k]}")
            return {"cols": [c[1] for c in cols], "rows": {n: v for n, v in out.items() if n != "TOTAL"}, "total": out["TOTAL"]}
    return None


def extract(pages):
    return {"industry": table(pages, r"JOB CUTS BY INDUSTRY"),
            "reason": table(pages, r"JOB CUTS BY REASON"),
            "hiring": table(pages, r"HIRING PLANS")}


def pages_from_pdf(blob):
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for pg in pdf.pages:
            out.append({"words": [[w["x0"], w["x1"], w["top"], w["text"]] for w in pg.extract_words()]})
    return out


def merge(D, T, month):
    """Grava o que o relatorio de `month` traz; o relatorio mais novo prevalece."""
    if T.get("industry"):
        for name, vals in T["industry"]["rows"].items():
            for c, v in zip(T["industry"]["cols"], vals):
                if not c.startswith("YTD"):
                    D["industry"].setdefault(name, {})[c] = v
        D["industry_ytd"] = {"month": month, "cols": T["industry"]["cols"], "rows": T["industry"]["rows"]}
    if T.get("reason"):
        i = T["reason"]["cols"].index(month) if month in T["reason"]["cols"] else 0
        for name, vals in T["reason"]["rows"].items():
            D["reason"].setdefault(name, {})[month] = vals[i]
        D["reason_ytd"] = {"month": month, "cols": T["reason"]["cols"], "rows": T["reason"]["rows"]}
    if T.get("hiring"):
        i = T["hiring"]["cols"].index(month) if month in T["hiring"]["cols"] else 0
        for name, vals in T["hiring"]["rows"].items():
            D["hiring"].setdefault(name, {})[month] = vals[i]
        D["hiring_ytd"] = {"month": month, "cols": T["hiring"]["cols"], "rows": T["hiring"]["rows"]}
    return D


def load():
    if DATA.exists():
        return json.load(open(DATA))
    return {"industry": {}, "reason": {}, "hiring": {}}


def save(D):
    json.dump(D, open(DATA, "w"), separators=(",", ":"))
