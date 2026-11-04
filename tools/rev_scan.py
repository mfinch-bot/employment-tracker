"""Levantamento unico: baixa so as pastas ja divulgadas (abr/26 e set/26). Sera apagado."""
import pathlib, urllib.request
B = "https://info0.s3.us-east-2.amazonaws.com/rpls/"
FILES = ["employment_national.csv", "employment_naics.csv", "table_b_naics.csv", "employment_foreign_domestic_workers.csv",
         "employment_all_granularities.csv", "bls_revisions.csv", "employment_national_history.csv"]
for folder in ("202604", "202609"):
    p = pathlib.Path("data/rev_scan") / folder
    p.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        try:
            with urllib.request.urlopen(f"{B}{folder}/employment/{f}", timeout=60) as r:
                b = r.read()
            if f == "employment_all_granularities.csv":
                b = b"\n".join(b.split(b"\n")[:4000])
            (p / f).write_bytes(b)
            print(folder, f, len(b))
        except Exception as e:
            print(folder, f, "ERRO", e)
