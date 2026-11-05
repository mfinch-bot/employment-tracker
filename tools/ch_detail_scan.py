"""Levantamento unico: posicao das palavras nas paginas das tabelas 2, 4 e 7 de cada relatorio (sera apagado)."""
import io, json, pathlib, re, urllib.request
import pdfplumber
B = "https://www.challengergray.com/wp-json/wp/v2/posts?categories=61&per_page=30&_fields=date_gmt,content&page="
def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; employment-tracker)"})
    import time
    for tent in range(4):
        try:
            with urllib.request.urlopen(r, timeout=60) as x:
                return x.read()
        except Exception as e:
            print("tentativa", tent, e)
            time.sleep(20)
    raise RuntimeError(u)
out = []
for page in (1,):
    for p in json.loads(get(B + str(page))):
        l = re.findall(r'href="([^"]+\.pdf)"', p["content"]["rendered"])
        if not l:
            continue
        try:
            blob = get(l[0])
        except Exception as e:
            print("erro", l[0], e)
            continue
        rec = {"date": p["date_gmt"][:10], "pdf": l[0], "pages": []}
        with pdfplumber.open(io.BytesIO(blob)) as pdf:
            for n, pg in enumerate(pdf.pages):
                t = (pg.extract_text() or "").upper()
                if not re.search(r"TABLE\s*[247]\s*:", t) and "BY REASON" not in t and "HIRING PLANS" not in t:
                    continue
                words = [[round(w["x0"], 1), round(w["x1"], 1), round(w["top"], 1), w["text"]] for w in pg.extract_words()]
                rec["pages"].append({"n": n + 1, "width": pg.width, "words": words})
        out.append(rec)
pathlib.Path("data/ch_detail_raw.json").write_text(json.dumps(out))
print(len(out))
