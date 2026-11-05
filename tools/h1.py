"""Levantamento unico: series longas da FRED para comparar inicios de ciclo (sera apagado)."""
import pathlib, urllib.request, time, json
IDS="FEDFUNDS DFEDTARU DFEDTAR DFF DGS1 DGS2 DGS5 DGS10 T5YIE T10YIE T5YIFR DFII5 DFII10 TB3MS GS2 GS1 UNRATE NROU AHETPI CES0500000003 ECIWAG ECIALLCIV ULCNFB OPHNFB CPILFESL CPIAUCSL PCEPILFE PCEPI PAYEMS CLF16OV ICSA CCSA GDPC1 CIVPART LNS11300060 JTSJOL UNEMPLOY DCOILWTICO USREC BAMLH0A0HYM2 THREEFYTP10".split()
out={}
for s in IDS:
    for t in range(3):
        try:
            r=urllib.request.Request(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}",headers={"User-Agent":"Mozilla/5.0 (compatible; employment-tracker)","Accept":"*/*"})
            txt=urllib.request.urlopen(r,timeout=60).read().decode()
            L=txt.strip().split("\n")[1:];d={}
            for l in L:
                a,b=l.split(",")[:2]
                if b not in("",".","NA"):d[a]=float(b)
            out[s]=d;print(s,len(d),max(d),d[max(d)]);break
        except Exception as e:
            print(s,"erro",e);time.sleep(5)
pathlib.Path("data/h1.json").write_text(json.dumps(out))
