"""Levantamento unico: o que existe publico de futuros (sera apagado)."""
import json, pathlib, urllib.request, time
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept":"application/json,text/html,*/*"}
def get(u):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25);return r.status,r.read()
    except Exception as e:
        return getattr(e,'code','ERR '+type(e).__name__),b''
for u in ("https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/305/G","https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/305/FUT?strategy=DEFAULT&tradeDate=11/04/2026&pageSize=50","https://www.cmegroup.com/markets/interest-rates/stirs/30-day-federal-fund.settlements.html","https://www.cmegroup.com/ftp/settle/","https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"):
    c,b=get(u);print(u[:90],c,len(b),b[:120])
MC="FGHJKMNQUVXZ";o={}
t0=int(time.mktime((2025,12,15,0,0,0,0,0,0)));t1=int(time.time())
for root,suf,yrs,ms in (("ZQ",".CBT",(26,27,28),MC),("SR3",".CME",(26,27,28,29),"HMUZ")):
    for y in yrs:
        for m in ms:
            k=f"{root}{m}{y}{suf}";c,b=get(f"https://query1.finance.yahoo.com/v8/finance/chart/{k}?period1={t0}&period2={t1}&interval=1d")
            n=None
            if c==200:
                try:
                    r=json.loads(b)["chart"]["result"][0];ts=r.get("timestamp") or [];cl=r["indicators"]["quote"][0].get("close") or []
                    o[k]={time.strftime("%Y-%m-%d",time.gmtime(a)):v for a,v in zip(ts,cl) if v is not None};n=len(o[k])
                except Exception as e:n=str(e)
            print(k,c,n,(max(o[k]),o[k][max(o[k])]) if o.get(k) else None);time.sleep(.3)
pathlib.Path("data/f1.json").write_text(json.dumps(o))
