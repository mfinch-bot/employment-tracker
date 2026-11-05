import json, pathlib, urllib.request
import openpyxl, io
u="https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/wage-growth-tracker/wage-growth-data.xlsx"
r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0 (compatible; employment-tracker)"})
b=urllib.request.urlopen(r,timeout=60).read()
wb=openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=True)
out={}
for ws in wb:
    rows=list(ws.iter_rows(values_only=True))
    out[ws.title]={"n":len(rows),"head":[[str(c)[:40] for c in row[:14]] for row in rows[:6]],"tail":[[str(c)[:12] for c in row[:14]] for row in rows[-2:]]}
pathlib.Path("data/atl.json").write_text(json.dumps(out))
