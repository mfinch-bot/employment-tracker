"""Levantamento unico: le todos os PDFs de relatorios e guarda as tabelas (sera apagado)."""
import io, json, pathlib, re, urllib.request
from pypdf import PdfReader
B = "https://www.challengergray.com/wp-json/wp/v2/posts?categories=61&per_page=100&_fields=date_gmt,title,content&page="
def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; employment-tracker)"})
    with urllib.request.urlopen(r, timeout=60) as x:
        return x.read()
out = []
for page in (1, 2, 3):
    for p in json.loads(get(B + str(page))):
        l = re.findall(r'href="([^"]+\.pdf)"', p["content"]["rendered"])
        if not l:
            continue
        try:
            t = "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(get(l[0]))).pages)
        except Exception as e:
            out.append({"date": p["date_gmt"][:10], "pdf": l[0], "error": str(e)})
            continue
        out.append({"date": p["date_gmt"][:10], "pdf": l[0], "text": t})
pathlib.Path("data/ch_scan.json").write_text(json.dumps(out))
print(len(out))
