"""Robo do release: espera o dado novo, confere e so entao publica o dashboard.

Modos:
  --watch  consulta o BLS a partir de 8:29 ET no dia de divulgacao
  --once   confere uma vez (rodada de seguranca e testes)
"""
import datetime as dt, json, os, pathlib, sys, time
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import build_dashboard, calc, fetch_bls

ROOT = pathlib.Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
BRT = ZoneInfo("America/Sao_Paulo")
RELEASE_DATES = {"2026-11-06", "2026-12-04"}
PROBE = ["CES0000000001", "LNS13000000"]
POLL_SECONDS = 10
STOP_AT = dt.time(9, 15)


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
    print(kv)


def published_month():
    p = ROOT / "data/state.json"
    return json.load(open(p))["as_of"] if p.exists() else None


def is_release_day(now):
    day = now.date().isoformat()
    if now.year == 2026:
        return day in RELEASE_DATES
    # Sem calendario do ano: tenta nos dias uteis ate o dia 15 enquanto faltar o mes anterior
    return now.weekday() < 5 and now.day <= 15 and (published_month() or "") < calc.shift(day[:7], -1)


def next_release(now):
    day = now.date().isoformat()
    future = sorted(d for d in RELEASE_DATES if d > day or (d == day and now.astimezone(ET).time() < dt.time(8, 30)))
    if not future:
        return None
    y, m, d = map(int, future[0].split("-"))
    return dt.datetime(y, m, d, 8, 30, tzinfo=ET).isoformat()


def validate(L, as_of):
    """Devolve a lista de problemas. Lista vazia libera a publicacao."""
    errs = []
    def v(c, m=as_of):
        return L[c].get(m)
    for c in build_dashboard.REQUIRED:
        if v(c) is None:
            errs.append(f"coluna {c} sem {as_of}")
    if errs:
        return errs
    checks = [("Nonfarm = Private + Government", v("B"), v("C") + v("P")),
              ("Government = Federal + State + Local", v("P"), v("Q") + v("R") + v("S")),
              ("Private = setores", v("C"), sum(v(c) for c in "E F G I J K L M N O".split())),
              ("Education and Health = Health + Education", v("M"), v("W") + v("AB")),
              ("Population = Labor Force + Not in LF", v("AU"), v("AV") + v("BA"))]
    for name, a, b in checks:
        if abs(a - b) > 3:
            errs.append(f"{name}: {a} x {b}")
    u = v("AZ") / v("AV") * 100
    if abs(v("AV") / v("AU") * 100 - v("AW")) > 0.06:
        errs.append("Participation Rate nao fecha")
    if not 2 < u < 20:
        errs.append(f"U rate fora do normal: {u:.2f}")
    if abs(v("B") - L["B"][calc.shift(as_of, -1)]) > 3000:
        errs.append("Payroll com variacao fora do normal")
    return errs


def publish(raw, as_of, first_seen=None):
    now = dt.datetime.now(BRT)
    json.dump(raw, open(ROOT / "data/raw.json", "w"), separators=(",", ":"))
    build_dashboard.render(raw, as_of=as_of, published=now)
    state = {"as_of": as_of, "published": now.isoformat(timespec="seconds"), "next_release": next_release(now)}
    json.dump(state, open(ROOT / "data/state.json", "w"))
    json.dump(state, open(ROOT / "docs/state.json", "w"))
    if first_seen:
        with open(ROOT / "data/log.jsonl", "a") as f:
            f.write(json.dumps({"as_of": as_of, "first_seen": first_seen.isoformat(timespec="seconds"),
                                "built": now.isoformat(timespec="seconds")}) + "\n")
    output(changed="true", as_of=as_of)


def fetch_and_check(key):
    raw = fetch_bls.fetch_all(key)
    L = calc.levels_from_raw(raw)
    as_of = calc.latest_month(L, build_dashboard.REQUIRED)
    return raw, as_of, validate(L, as_of)


def once(key):
    raw, as_of, errs = fetch_and_check(key)
    old_path = ROOT / "data/raw.json"
    old = json.load(open(old_path)) if old_path.exists() else None
    if errs:
        print("NAO PUBLICADO:", errs)
        output(changed="false")
        return 1
    if raw == old and (ROOT / "docs/index.html").exists() and "--force" not in sys.argv:
        print("Sem novidade.")
        output(changed="false")
        return 0
    publish(raw, as_of)
    return 0


def watch(key):
    now = dt.datetime.now(ET)
    if now.time() < dt.time(8, 0):
        print("Cedo demais; a proxima rodada assume.")
        output(changed="false")
        return 0
    if now.time() >= STOP_AT or not is_release_day(now):
        return once(key)
    target = calc.shift(now.date().isoformat()[:7], -1)
    if (published_month() or "") >= target:
        print("Release ja publicado.")
        output(changed="false")
        return 0
    start = now.replace(hour=8, minute=29, second=30, microsecond=0)
    if now < start:
        print("Aguardando ate", start)
        time.sleep((start - now).total_seconds())
    while dt.datetime.now(ET).time() < STOP_AT:
        try:
            out = fetch_bls.post(PROBE, target[:4], now.year, key)
        except SystemExit:
            time.sleep(POLL_SECONDS)
            continue
        seen = {s["seriesID"]: {f'{p["year"]}-{p["period"][1:]}' for p in s["data"]
                                if p["value"] not in ("-", "")} for s in out["Results"]["series"]}
        if all(target in seen.get(i, ()) for i in PROBE):
            first_seen = dt.datetime.now(BRT)
            print("Dado novo em", first_seen)
            for _ in range(20):
                raw, as_of, errs = fetch_and_check(key)
                if as_of >= target and not errs:
                    publish(raw, as_of, first_seen)
                    return 0
                print("Aguardando conferencia:", as_of, errs)
                time.sleep(POLL_SECONDS)
            print("Dado incompleto: mantido o release anterior")
            output(changed="false")
            return 1
        time.sleep(POLL_SECONDS)
    print("Dado nao apareceu ate", STOP_AT)
    output(changed="false")
    return 1


if __name__ == "__main__":
    key = os.environ["BLS_API_KEY"]
    sys.exit(watch(key) if "--watch" in sys.argv else once(key))
