"""Levantamento unico para o deck: series extras do BLS (sera apagado)."""
import json, os, pathlib, urllib.request, csv, io, time
KEY=os.environ["BLS_API_KEY"]
def api(ids, y0, y1):
    out={}
    for i in range(0,len(ids),50):
        body={"seriesid":ids[i:i+50],"startyear":str(y0),"endyear":str(y1),"registrationkey":KEY}
        r=urllib.request.Request("https://api.bls.gov/publicAPI/v2/timeseries/data/",json.dumps(body).encode(),{"Content-Type":"application/json"})
        J=json.load(urllib.request.urlopen(r,timeout=90))
        if J.get("message"): print(J["message"][:3])
        for s in J["Results"]["series"]:
            out[s["seriesID"]]={f"{d['year']}-{d['period'][1:]}":float(d["value"]) for d in s["data"] if d["period"].startswith("M") and d["period"]!="M13" and d["value"] not in ("","-")}
    return out
EXTRA={"unemp_rate":"LNS14000000","job_losers":"LNS13023621","job_leavers":"LNS13023705","reentrants":"LNS13023557","new_entrants":"LNS13023569",
"median_dur":"LNS13008275","lt27":"LNS13025703","part_time_econ":"LNS12032194","fb_clf":"LNU01073395","nb_clf":"LNU01073413","fb_emp":"LNU02073395","nb_emp":"LNU02073413","fb_pop":"LNU00073395","nb_pop":"LNU00073413",
"lfpr_2554":"LNS11300060","epop_2554":"LNS12300060","cpi":"CUSR0000SA0","core":"CUSR0000SA0L1E","aggr_hours":"CES0500000036","aggr_pay":"CES0500000017"}
ids=list(EXTRA.values())
data={}
for y0,y1 in ((2007,2026),):
    d=api(ids,y0,y1)
    for k,v in EXTRA.items(): data[k]=d.get(v,{})
# Difusao: setores de 3 digitos NAICS
hdr={"User-Agent":"Mozilla/5.0 (compatible; employment-tracker)","Accept":"*/*"}
txt=urllib.request.urlopen(urllib.request.Request("https://download.bls.gov/pub/time.series/ce/ce.industry",headers=hdr),timeout=90).read().decode("latin1")
rows=list(csv.DictReader(io.StringIO(txt),delimiter="\t"))
print(rows[0])
sel=[(r["industry_code"].strip(),r["industry_name"].strip(),r["naics_code"].strip()) for r in rows if len(r.get("naics_code","").strip())==3 and r["naics_code"].strip().isdigit() and r["industry_code"].strip()[:2] not in ("90","00")]
print(len(sel),sel[:3])
ind=[f"CES{c}01" for c,_,_ in sel]
d=api(ind,2023,2026)
data["diff"]={f"{n} ({na})":d.get(f"CES{c}01",{}) for c,n,na in sel}
print(sum(1 for v in data["diff"].values() if v))
pathlib.Path("data/deck.json").write_text(json.dumps(data))
print({k:(max(v),v[max(v)]) for k,v in data.items() if k!="diff" and v},[k for k,v in data.items() if not v])
