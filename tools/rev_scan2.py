"""Levantamento unico da pasta ja divulgada de out/26 (sera apagado)."""
import pathlib, urllib.request
B = "https://info0.s3.us-east-2.amazonaws.com/rpls/202610/"
FILES = ["postings/postings_total_us.csv", "postings/postings_by_sector.csv", "postings/sector_summary.csv",
         "hiring_attrition/hiring_and_attrition_total_us.csv", "hiring_attrition/hiring_and_attrition_by_sector.csv",
         "salaries/salaries_national.csv", "salaries/salary_overview_total.csv", "salaries/salaries_naics.csv",
         "layoffs/total_layoffs.csv", "layoffs/layoffs_by_naics.csv",
         "employment/employment_foreign_domestic_workers.csv", "employment/employment_soc.csv",
         "employment/employment_national.csv", "employment/employment_naics.csv",
         "employment/employment_national_history.csv", "employment/bls_revisions.csv"]
out = pathlib.Path("data/rev_scan2")
for f in FILES:
    p = out / f
    p.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(B + f, timeout=60) as r:
        p.write_bytes(r.read())
    print(f, p.stat().st_size)
