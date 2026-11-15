"""Agrupa ofertas de distintas tiendas que son el mismo producto.

1. Mismo EAN (código de barras) -> mismo producto. Es el match fuerte.
2. Los EAN compartidos enseñan alias de marca (p. ej. "Paco Rabanne" = "Rabanne").
3. Misma marca + misma clave de nombre (tokens + concentración + ml) -> mismo
   producto, salvo que el grupo mezcle géneros explícitos distintos.
"""
import hashlib
from collections import defaultdict


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def group(offers):
    """offers: lista de dicts con id, store, ean, brand, key, gender, kind.
    Devuelve lista de productos: {id, match, offers:[...]}"""
    uf, brands = UF(), UF()
    by_ean = defaultdict(list)
    for o in offers:
        uf.find(o["id"])
        if o["ean"]:
            by_ean[o["ean"]].append(o)
    for same in by_ean.values():
        for o in same[1:]:
            uf.union(same[0]["id"], o["id"])
            if same[0]["brand"] and o["brand"]:
                brands.union(same[0]["brand"], o["brand"])

    by_key = defaultdict(list)
    for o in offers:
        if o["key"] and o["brand"]:
            by_key[(brands.find(o["brand"]), o["key"])].append(o)
    for same in by_key.values():
        genders = {o["gender"] for o in same if o["gender"]}
        if len(genders) <= 1:
            pools = [same]
        else:  # mezcla M/F: solo unir los que declaran el mismo género
            pools = [[o for o in same if o["gender"] == g] for g in genders]
        for pool in pools:
            for o in pool[1:]:
                uf.union(pool[0]["id"], o["id"])

    groups = defaultdict(list)
    for o in offers:
        groups[uf.find(o["id"])].append(o)

    products = []
    for members in groups.values():
        eans = sorted({o["ean"] for o in members if o["ean"]})
        stores = {o["store"] for o in members}
        if len(stores) < 2:
            match = "single"
        else:
            # "ean" si todas las tiendas quedan conectadas por código de barras
            ean_stores = defaultdict(set)
            for o in members:
                if o["ean"]:
                    ean_stores[o["ean"]].add(o["store"])
            match = "ean" if any(s == stores for s in ean_stores.values()) else "nombre"
        anchor = eans[0] if eans else min(
            f"{o['brand']}|{o['key']}|{o['gender']}" if o["key"] else f"{o['store']}|{o['sku']}"
            for o in members)
        pid = hashlib.sha1(anchor.encode()).hexdigest()[:10]
        products.append({"id": pid, "match": match, "offers": members})
    return products
