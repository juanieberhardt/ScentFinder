"""Lee la base y genera el sitio estático (public/): data.json + history.json."""
import json
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from . import config, match, opportunities

SITE = Path(__file__).resolve().parent.parent / "site"


def build(con, out_dir, today=None):
    today = today or date.today()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    history = defaultdict(list)
    for r in con.execute("SELECT offer_id, date, price, in_stock FROM prices ORDER BY offer_id, date"):
        history[r["offer_id"]].append((r["date"], r["price"], r["in_stock"]))

    offers = []
    for r in con.execute("SELECT * FROM offers WHERE kind != 'other'"):
        h = history.get(r["id"])
        if not h:
            continue
        o = dict(r)
        o["price"], o["in_stock"] = h[-1][1], bool(h[-1][2])
        lp = con.execute("SELECT list_price FROM prices WHERE offer_id=? ORDER BY date DESC LIMIT 1",
                         (r["id"],)).fetchone()
        o["list_price"] = lp[0] if lp else o["price"]
        offers.append(o)

    products, hist_out = [], {}
    for p in match.group(offers):
        ev = opportunities.evaluate(p, history, today)
        if not ev:  # nada en stock en ninguna tienda
            continue
        # una oferta por tienda (la más barata en stock; si no hay, la más barata)
        per_store = {}
        for o in sorted(p["offers"], key=lambda o: (not o["in_stock"], o["price"])):
            per_store.setdefault(o["store"], o)
        shown = sorted(per_store.values(), key=lambda o: (not o["in_stock"], o["price"]))
        best = next(o for o in p["offers"] if o["id"] == ev["best_offer"])
        # nombre para mostrar: el más descriptivo entre las tiendas
        ref = max(p["offers"], key=lambda o: (bool(o["ean"]), len(o["name"])))
        products.append({
            "id": p["id"],
            "brand": (ref["brand_raw"] or "").strip().title(),
            "name": ref["name"],
            "ml": best["ml"], "conc": best["conc"], "gender": best["gender"],
            "kind": best["kind"], "img": best["image"] or ref["image"],
            "match": p["match"],
            "price": best["price"], "store": best["store"],
            "offers": [{"s": o["store"], "p": o["price"], "l": o["list_price"],
                        "u": o["url"], "k": int(o["in_stock"]), "n": o["name"]} for o in shown],
            "gap": ev["gap"], "drop": ev["drop"], "usual": ev["usual"], "atl": ev["atl"],
            "opp": ev["is_opp"], "score": ev["score"], "verify": ev["verify"],
        })
        hist_out[p["id"]] = {o["store"]: [[d, pr, k] for d, pr, k in history[o["id"]]] for o in shown}

    products.sort(key=lambda p: -p["score"])
    runs = [dict(r) for r in con.execute(
        "SELECT * FROM runs WHERE date=(SELECT MAX(date) FROM runs)")]
    data = {
        "generated": today.isoformat(),
        "stores": {k: {"name": v["name"], "url": v["base"]} for k, v in config.STORES.items()},
        "runs": runs,
        "products": products,
    }
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    (out / "history.json").write_text(json.dumps(hist_out, separators=(",", ":")), "utf-8")
    shutil.copy(SITE / "index.html", out / "index.html")
    n_opp = sum(1 for p in products if p["opp"])
    multi = sum(1 for p in products if len(p["offers"]) > 1)
    return {"products": len(products), "multi_store": multi, "opportunities": n_opp}
