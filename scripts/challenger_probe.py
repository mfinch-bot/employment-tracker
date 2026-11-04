"""Teste: le os ultimos relatorios da Challenger e guarda o trecho das tabelas."""
import json, re, subprocess, sys, urllib.request, io, pathlib
from pypdf import PdfReader
B = "https://www.challengergray.com"
def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; employment-tracker)"})
    with urllib.request.urlopen(r, timeout=40) as x:
        return x.read(), dict(x.headers)
raw, h = get(B + "/wp-json/wp/v2/posts?categories=61&per_page=6&_fields=date,date_gmt,link,title,content")
posts = json.loads(raw)
out = ["headers " + str({k: v for k, v in h.items() if k.lower() in ("cache-control", "age", "x-cache", "server", "x-pantheon-styx-hostname")})]
for p in posts:
    html = p["content"]["rendered"]
    pdf = re.findall(r'href="([^"]+\.pdf)"', html)
    out.append(f"## {p['date']} {p['date_gmt']} {p['title']['rendered'][:70]} pdf={pdf[:1]}")
    if not pdf:
        continue
    blob, _ = get(pdf[0])
    txt = [pg.extract_text() or "" for pg in PdfReader(io.BytesIO(blob)).pages]
    out.append(f"pages={len(txt)}")
    all_txt = "\n".join(txt)
    for m in re.finditer(r"(?m)^.*(Government|Total|TOTAL|Hiring|hiring).*$", all_txt):
        line = m.group(0)
        if re.search(r"\d", line) and len(line) < 160:
            out.append(line)
pathlib.Path("data/ch_probe.txt").write_text("\n".join(out)[:60000])
print("ok", len(posts))
