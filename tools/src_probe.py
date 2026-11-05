"""Teste unico de acesso as fontes originais (sera apagado)."""
import json, os, pathlib, urllib.request
out = {}
URLS = {
 "dol_ar539": "https://oui.doleta.gov/unemploy/csv/ar539.csv",
 "dol_pdf": "https://www.dol.gov/ui/data.pdf",
 "dol_page": "https://oui.doleta.gov/unemploy/claims.asp",
 "fred_icsa": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=ICSA",
 "atlanta": "https://www.atlantafed.org/-/media/documents/datafiles/chcs/wage-growth-tracker/wage-growth-data.xlsx",
 "atlanta_page": "https://www.atlantafed.org/chcs/wage-growth-tracker",
 "nyfed": "https://www.newyorkfed.org/medialibrary/interactives/sce/sce/downloads/data/frbny-sce-data.xlsx",
 "nyfed_page": "https://www.newyorkfed.org/microeconomics/sce",
 "bls_cd": "https://download.bls.gov/pub/time.series/cd/cd.series",
 "nfib": "https://www.nfib.com/news/monthly_report/sbet/",
 "cb": "https://www.conference-board.org/topics/consumer-confidence",
 "ism": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/",
}
for k, u in URLS.items():
    try:
        r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; employment-tracker)", "Accept": "*/*"})
        with urllib.request.urlopen(r, timeout=40) as x:
            b = x.read()
        out[k] = {"status": x.status, "type": x.headers.get("content-type"), "len": len(b), "head": b[:220].decode("latin1"), "tail": b[-200:].decode("latin1") if "csv" in u else ""}
        p = pathlib.Path("data/probe"); p.mkdir(exist_ok=True)
        if k in ("dol_pdf", "atlanta", "nyfed", "dol_page", "atlanta_page", "nyfed_page", "nfib", "cb", "bls_cd"):
            (p / (k + (".pdf" if k == "dol_pdf" else ".xlsx" if u.endswith("xlsx") else ".txt"))).write_bytes(b[:6000000])
    except Exception as e:
        out[k] = {"erro": f"{type(e).__name__} {e}"[:150]}
# BLS: ids candidatos
S = ["CIU1010000000000A","CIU2010000000000A","CIU2020000000000A","CIS2010000000000Q","CIS1010000000000Q","CIS2020000000000Q","CIU2020000000000Q","CIS2020000000000I",
     "PRS85006112","PRS85006092","PRS85006113","PRS85006093","LNS13327709","LNS14000000"]
req = urllib.request.Request("https://api.bls.gov/publicAPI/v2/timeseries/data/", json.dumps({"seriesid": S, "startyear": "2024", "endyear": "2026", "registrationkey": os.environ.get("BLS_API_KEY", "")}).encode(), {"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as x:
        J = json.load(x)
    out["bls"] = {"status": J.get("status"), "msg": J.get("message"), "series": {s["seriesID"]: (s["data"][0]["year"] + s["data"][0]["period"], s["data"][0]["value"]) if s["data"] else None for s in J.get("Results", {}).get("series", [])}}
except Exception as e:
    out["bls"] = {"erro": str(e)}
pathlib.Path("data/probe").mkdir(exist_ok=True)
pathlib.Path("data/probe/result.json").write_text(json.dumps(out, indent=1))
