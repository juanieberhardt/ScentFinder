"""Uso:
  python -m scentfinder.run                 # scrapea todas las tiendas y genera public/
  python -m scentfinder.run --stores rouge  # solo algunas
  python -m scentfinder.run --build-only    # regenera el sitio sin scrapear
"""
import argparse
import sys
from datetime import date, datetime, timedelta, timezone

from . import build, config, db, normalize, scrapers


def today_ar():
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date()  # hora Argentina


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/prices.db")
    ap.add_argument("--out", default="public")
    ap.add_argument("--stores", nargs="*", default=list(config.STORES))
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    today = today_ar()
    ok = 0
    if not args.build_only:
        for sid in args.stores:
            print(f"[{sid}] scrapeando…", flush=True)
            try:
                raws = scrapers.scrape(sid)
                parsed = [(r, normalize.parse(r)) for r in raws]
                note = db.save_store(con, sid, today.isoformat(), parsed, config.MIN_COVERAGE)
                stock = sum(1 for r in raws if r["in_stock"])
                print(f"[{sid}] {len(raws)} ofertas, {stock} en stock. {note}", flush=True)
                ok += 1
            except Exception as e:  # una tienda caída no frena a las demás
                print(f"[{sid}] ERROR: {e}", flush=True)
                con.rollback()
                con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
                            (today.isoformat(), sid, 0, 0, str(e)[:300]))
                con.commit()
        if ok == 0:
            print("Ninguna tienda respondió; no se publica.")
            return 1
    stats = build.build(con, args.out, today)
    print("Sitio generado:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
