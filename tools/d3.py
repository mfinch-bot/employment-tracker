"""Levantamento unico (sera apagado)."""
import json, os, pathlib, urllib.request
E={"pop":"LNS10000000","clf_1624":"LNS11024887","clf_2554":"LNS11000060","clf_55":"LNS11024230","un_1624":"LNS13024887","un_2554":"LNS13000060","un_55":"LNS13024230","ep":"LNS12300000","ep_2554":"LNS12300060","want":"LNS15026639","u6":"LNS13327709","pt_econ":"LNS12032194"}
b={"seriesid":list(E.values()),"startyear":"2019","endyear":"2026","registrationkey":os.environ["BLS_API_KEY"]}
J=json.load(urllib.request.urlopen(urllib.request.Request("https://api.bls.gov/publicAPI/v2/timeseries/data/",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=90))
print(J.get("message"))
rv={v:k for k,v in E.items()};o={}
for s in J["Results"]["series"]:
    o[rv[s["seriesID"]]]={f"{d['year']}-{d['period'][1:]}":float(d["value"]) for d in s["data"] if d["period"].startswith("M") and d["value"] not in("","-")}
pathlib.Path("data/d3.json").write_text(json.dumps(o));print({k:(max(v),v[max(v)]) for k,v in o.items()})
