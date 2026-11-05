"""Levantamento unico de coortes (sera apagado)."""
import json, os, pathlib, urllib.request
E={"u_1624":"LNS14024887","u_2554":"LNS14000060","u_55":"LNS14024230","l_1624":"LNS11324887","l_2554":"LNS11300060","l_55":"LNS11324230",
"u_lhs":"LNS14027659","u_hs":"LNS14027660","u_sc":"LNS14027689","u_ba":"LNS14027662","l_lhs":"LNS11327659","l_hs":"LNS11327660","l_sc":"LNS11327689","l_ba":"LNS11327662",
"u_men":"LNS14000025","u_wom":"LNS14000026","l_men":"LNS11300025","l_wom":"LNS11300026","u_all":"LNS14000000","l_all":"LNS11300000","emp":"LNS12000000","clf":"LNS11000000"}
b={"seriesid":list(E.values()),"startyear":"2015","endyear":"2026","registrationkey":os.environ["BLS_API_KEY"]}
J=json.load(urllib.request.urlopen(urllib.request.Request("https://api.bls.gov/publicAPI/v2/timeseries/data/",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=90))
print(J.get("message"))
rv={v:k for k,v in E.items()};o={}
for s in J["Results"]["series"]:
    o[rv[s["seriesID"]]]={f"{d['year']}-{d['period'][1:]}":float(d["value"]) for d in s["data"] if d["period"].startswith("M") and d["value"] not in("","-")}
pathlib.Path("data/d2.json").write_text(json.dumps(o));print({k:(max(v),v[max(v)]) for k,v in o.items()})
