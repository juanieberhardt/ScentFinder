"""Scrapers por plataforma. Usan las APIs públicas de catálogo de cada tienda
(VTEX catalog_system y Magento GraphQL), no parsean HTML.

Cada scraper devuelve una lista de dicts "raw offer":
  sku, ean, brand, name, url, image, price, list_price, in_stock, gender_hint, hint
"""
import json
import time

import requests

from . import config

VTEX_MAX_WINDOW = 2500  # VTEX no deja paginar más allá de _from=2500
VTEX_PAGE = 50


class Http:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "es-AR,es;q=0.9",
        })

    def get(self, url, params=None):
        last = None
        for attempt in range(config.MAX_RETRIES):
            try:
                r = self.s.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
                if r.status_code in (200, 206):
                    time.sleep(config.REQUEST_DELAY)
                    return r
                last = f"HTTP {r.status_code}"
                if r.status_code in (400, 404):
                    break
            except requests.RequestException as e:
                last = repr(e)
            time.sleep(2 ** attempt * 1.5)
        raise RuntimeError(f"GET {url} {params or ''} falló: {last}")


# ---------------------------------------------------------------- VTEX

def _vtex_total(http, base, path, extra=None):
    params = {"fq": f"C:/{path}/", "_from": 0, "_to": 0, **(extra or {})}
    r = http.get(f"{base}/api/catalog_system/pub/products/search", params)
    res = r.headers.get("resources", "")  # "0-0/5521"
    try:
        return int(res.split("/")[1])
    except (IndexError, ValueError):
        return len(r.json())


def _vtex_pages(http, base, path, total, extra=None):
    for start in range(0, min(total, VTEX_MAX_WINDOW), VTEX_PAGE):
        params = {"fq": f"C:/{path}/", "_from": start,
                  "_to": start + VTEX_PAGE - 1, **(extra or {})}
        page = http.get(f"{base}/api/catalog_system/pub/products/search", params).json()
        if not page:
            return
        yield from page


def _vtex_walk(http, base, node, path, log):
    """Baja por el árbol de categorías hasta que cada rama entre en la ventana de 2500."""
    total = _vtex_total(http, base, path)
    if total == 0:
        return
    if total <= VTEX_MAX_WINDOW:
        yield from _vtex_pages(http, base, path, total)
    elif node.get("children"):
        for ch in node["children"]:
            yield from _vtex_walk(http, base, ch, f"{path}/{ch['id']}", log)
    else:
        # hoja con >2500: barrer por precio ascendente y descendente (cubre 5000)
        log(f"  categoría {path} tiene {total} productos; barrido doble por precio")
        for order in ("OrderByPriceASC", "OrderByPriceDESC"):
            yield from _vtex_pages(http, base, path, total, {"O": order})


def _find_node(tree, cat_id):
    for n in tree:
        if n["id"] == cat_id:
            return n
        hit = _find_node(n.get("children") or [], cat_id)
        if hit:
            return hit
    return None


def scrape_vtex(store, log=print):
    http = Http()
    base = store["base"]
    tree = http.get(f"{base}/api/catalog_system/pub/category/tree/6").json()
    out, seen = [], set()
    for cat_id in store["categories"]:
        node = _find_node(tree, cat_id) or {"id": cat_id, "children": []}
        expected = _vtex_total(http, base, str(cat_id))
        products = set()
        for p in _vtex_walk(http, base, node, str(cat_id), log):
            products.add(p.get("productId"))
            cats = " ".join(p.get("categories") or [])
            for it in p.get("items") or []:
                sku = str(it.get("itemId"))
                if sku in seen:
                    continue
                seen.add(sku)
                offer = ((it.get("sellers") or [{}])[0]).get("commertialOffer") or {}
                price = float(offer.get("Price") or 0)
                imgs = it.get("images") or [{}]
                out.append({
                    "sku": sku,
                    "ean": it.get("ean") or "",
                    "brand": p.get("brand") or "",
                    "name": it.get("nameComplete")
                            or f"{p.get('productName', '')} {it.get('name', '')}",
                    "url": p.get("link") or "",
                    "image": imgs[0].get("imageUrl") or "",
                    "price": price,
                    "list_price": float(offer.get("ListPrice") or 0) or price,
                    "in_stock": bool(price > 0 and (offer.get("AvailableQuantity") or 0) > 0),
                    "gender_hint": cats,
                    "hint": cats,
                })
        if expected and len(products) < expected * 0.95:
            log(f"  AVISO categoría {cat_id}: {len(products)} de {expected} productos")
    return out


# ---------------------------------------------------------------- Magento

_MAGENTO_Q = """{products(filter:{category_id:{eq:"%s"}},pageSize:100,currentPage:%d){
 total_count page_info{total_pages}
 items{sku name url_key url_suffix stock_status %s
  small_image{url}
  price_range{minimum_price{regular_price{value} final_price{value}}}}}}"""

_ATTR_Q = """{customAttributeMetadata(attributes:[%s]){
 items{attribute_code attribute_options{label value}}}}"""


def _gql(http, base, query):
    r = http.get(f"{base}/graphql", {"query": query})
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(f"GraphQL: {json.dumps(data['errors'])[:300]}")
    return data["data"]


def scrape_magento(store, log=print):
    http = Http()
    base = store["base"]
    attrs = [a for a in (store.get("brand_attr"), store.get("gender_attr")) if a]
    opts = {}
    if attrs:
        q = _ATTR_Q % ",".join(
            '{attribute_code:"%s",entity_type:"catalog_product"}' % a for a in attrs)
        for item in _gql(http, base, q)["customAttributeMetadata"]["items"]:
            opts[item["attribute_code"]] = {
                str(o["value"]): o["label"] for o in item.get("attribute_options") or []}
    out, seen = [], set()
    for cat in store["categories"]:
        page, pages = 1, 1
        while page <= pages:
            d = _gql(http, base, _MAGENTO_Q % (cat, page, " ".join(attrs)))["products"]
            pages = d["page_info"]["total_pages"]
            for p in d["items"]:
                if p["sku"] in seen:
                    continue
                seen.add(p["sku"])
                mp = p["price_range"]["minimum_price"]
                price = float(mp["final_price"]["value"] or 0)
                brand = opts.get(store.get("brand_attr"), {}).get(str(p.get(store.get("brand_attr"))), "")
                gender = opts.get(store.get("gender_attr"), {}).get(str(p.get(store.get("gender_attr"))), "")
                out.append({
                    "sku": p["sku"],
                    "ean": "",
                    "brand": brand,
                    "name": p["name"],
                    "url": f"{base}/{p['url_key']}{p.get('url_suffix') or ''}",
                    "image": (p.get("small_image") or {}).get("url") or "",
                    "price": price,
                    "list_price": float(mp["regular_price"]["value"] or 0) or price,
                    "in_stock": p.get("stock_status") == "IN_STOCK" and price > 0,
                    "gender_hint": gender,
                    "hint": "",
                })
            page += 1
    return out


SCRAPERS = {"vtex": scrape_vtex, "magento": scrape_magento}


def scrape(store_id, log=print):
    store = config.STORES[store_id]
    return SCRAPERS[store["platform"]](store, log)
