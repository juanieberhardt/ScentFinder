"""Algoritmo de oportunidades.

Para la mejor oferta en stock de cada producto se calculan dos señales:

  gap  = 1 - precio / mediana(mejor precio de cada una de las OTRAS tiendas)
         -> qué tan barato está respecto del resto del mercado hoy.
  drop = 1 - precio / precio_habitual
         precio_habitual = mediana del precio diario de esa misma oferta en los
         últimos HIST_WINDOW_DAYS días (sin contar hoy, solo días con stock).
         -> qué tanto bajó respecto de lo que venía costando.

Además: "mínimo histórico" si el precio actual (vigente hace 7 días o menos) es el más bajo registrado.
El "precio de lista" tachado de la tienda NO se usa: suele estar inflado.

score = 100*gap + 80*drop + 5 si es mínimo histórico   (solo partes positivas)
"""
from datetime import date, timedelta
from statistics import median

from . import config


def daily_series(rows, today, days):
    """rows: [(date_iso, price, in_stock)] ordenadas (solo cambios).
    Devuelve precios diarios con stock en [today-days, today) con forward-fill."""
    if not rows:
        return []
    start = today - timedelta(days=days)
    out, i, cur = [], 0, None
    first = date.fromisoformat(rows[0][0])
    d = min(start, first)
    while d < today:
        while i < len(rows) and date.fromisoformat(rows[i][0]) <= d:
            cur = rows[i]
            i += 1
        if cur and cur[2] and d >= start:
            out.append(cur[1])
        d += timedelta(days=1)
    return out


def evaluate(product, history, today):
    """product: {match, offers:[{id, store, price, in_stock, ...}]}
    history: {offer_id: [(date, price, in_stock)]}. Devuelve dict o None."""
    best_by_store = {}
    for o in product["offers"]:
        if o["in_stock"] and o["price"] > 0:
            b = best_by_store.get(o["store"])
            if not b or o["price"] < b["price"]:
                best_by_store[o["store"]] = o
    if not best_by_store:
        return None
    best = min(best_by_store.values(), key=lambda o: o["price"])

    gap = None
    others = [o["price"] for s, o in best_by_store.items() if s != best["store"]]
    if others:
        gap = 1 - best["price"] / median(others)

    rows = history.get(best["id"], [])
    series = daily_series(rows, today, config.HIST_WINDOW_DAYS)
    drop, usual = None, None
    if len(series) >= config.HIST_MIN_DAYS:
        usual = median(series)
        drop = 1 - best["price"] / usual

    # mínimo histórico: el precio actual empezó hace <= 7 días y es menor a todo lo anterior
    atl = False
    if len(rows) > 1 and rows[-1][2]:
        prior = [r[1] for r in rows[:-1] if r[2]]
        age = (today - date.fromisoformat(rows[0][0])).days
        fresh = (today - date.fromisoformat(rows[-1][0])).days <= 7
        atl = bool(prior) and age >= config.ATL_MIN_DAYS and fresh and best["price"] < min(prior)

    is_opp = (gap or 0) >= config.MARKET_GAP_MIN or (drop or 0) >= config.HIST_DROP_MIN
    score = 100 * max(gap or 0, 0) + 80 * max(drop or 0, 0) + (5 if atl else 0)
    verify = product["match"] == "nombre" and (gap or 0) >= config.SUSPICIOUS_GAP

    return {
        "best_offer": best["id"],
        "gap": round(gap, 4) if gap is not None else None,
        "drop": round(drop, 4) if drop is not None else None,
        "usual": round(usual) if usual else None,
        "atl": atl,
        "is_opp": bool(is_opp),
        "score": round(score, 1),
        "verify": verify,
    }
