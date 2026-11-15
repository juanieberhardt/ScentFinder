"""SQLite: ofertas por tienda + historial de precios.

El historial guarda una fila solo cuando algo cambia (precio, precio de lista o
stock). El scraper corre todos los días; si no hay fila para un día, vale la
última anterior. Así la base queda chica y se puede versionar.
"""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
  id INTEGER PRIMARY KEY,
  store TEXT NOT NULL, sku TEXT NOT NULL,
  ean TEXT, brand_raw TEXT, brand TEXT, name TEXT, url TEXT, image TEXT,
  ml REAL, conc TEXT, gender TEXT, kind TEXT, key TEXT,
  first_seen TEXT, last_seen TEXT,
  UNIQUE(store, sku)
);
CREATE TABLE IF NOT EXISTS prices (
  offer_id INTEGER NOT NULL, date TEXT NOT NULL,
  price REAL, list_price REAL, in_stock INTEGER,
  PRIMARY KEY (offer_id, date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS runs (
  date TEXT, store TEXT, n_offers INTEGER, ok INTEGER, note TEXT,
  PRIMARY KEY (date, store)
);
"""


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def last_price(con, offer_id):
    return con.execute(
        "SELECT price, list_price, in_stock FROM prices WHERE offer_id=? "
        "ORDER BY date DESC LIMIT 1", (offer_id,)).fetchone()


def record_price(con, offer_id, date, price, list_price, in_stock):
    prev = last_price(con, offer_id)
    cur = (round(price, 2), round(list_price, 2), int(in_stock))
    if prev and (round(prev["price"], 2), round(prev["list_price"], 2), prev["in_stock"]) == cur:
        return False
    con.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?)", (offer_id, date, *cur))
    return True


def save_store(con, store, date, parsed_offers, min_coverage):
    """parsed_offers: lista de (raw, norm). Devuelve nota de estado."""
    prev_n = con.execute(
        "SELECT COUNT(*) FROM offers o WHERE store=? AND "
        "(SELECT in_stock FROM prices p WHERE p.offer_id=o.id ORDER BY date DESC LIMIT 1)=1",
        (store,)).fetchone()[0]
    seen = set()
    for raw, n in parsed_offers:
        con.execute(
            "INSERT INTO offers (store, sku, ean, brand_raw, brand, name, url, image, ml, conc,"
            " gender, kind, key, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(store, sku) DO UPDATE SET ean=excluded.ean, brand_raw=excluded.brand_raw,"
            " brand=excluded.brand, name=excluded.name, url=excluded.url, image=excluded.image,"
            " ml=excluded.ml, conc=excluded.conc, gender=excluded.gender, kind=excluded.kind,"
            " key=excluded.key, last_seen=excluded.last_seen",
            (store, raw["sku"], n["ean"], raw["brand"], n["brand"], raw["name"].strip(),
             raw["url"], raw["image"], n["ml"], n["conc"], n["gender"], n["kind"], n["key"],
             date, date))
        oid = con.execute("SELECT id FROM offers WHERE store=? AND sku=?",
                          (store, raw["sku"])).fetchone()[0]
        seen.add(oid)
        record_price(con, oid, date, raw["price"], raw["list_price"], raw["in_stock"])

    n_stock = sum(1 for raw, _ in parsed_offers if raw["in_stock"])
    note = ""
    if prev_n and n_stock < prev_n * min_coverage:
        note = f"cobertura baja ({n_stock} en stock vs {prev_n} ayer): no se dan de baja faltantes"
    else:
        # lo que no apareció hoy pasa a "sin stock"
        for row in con.execute("SELECT id FROM offers WHERE store=?", (store,)).fetchall():
            if row["id"] not in seen:
                lp = last_price(con, row["id"])
                if lp and lp["in_stock"]:
                    record_price(con, row["id"], date, lp["price"], lp["list_price"], 0)
    con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
                (date, store, len(parsed_offers), 1, note))
    con.commit()
    return note
