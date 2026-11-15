"""Genera una base de DEMO (datos de ejemplo, no reales) para probar el sitio sin scrapear.
Uso: python -m scentfinder.demo  ->  crea demo/prices.db y demo/public/
"""
import random
from datetime import date, timedelta
from pathlib import Path

from . import build, config, db, normalize

# (tienda, sku, ean, marca, nombre, precio base, pista de categoría)
ITEMS = [
    ("juleriaque", "j1", "3349668515660", "RABANNE", "Invictus EDT 100 ml", 256600, "/Fragancias/Premium/Masculinas/Eau de Toilette/"),
    ("rouge", "r1", "3349668515660", "Rabanne", "Invictus EDT 100 ml", 320750, "/Perfumes de hombre/"),
    ("parfumerie", "p1", "", "RABANNE", "INVICTUS EDT 100ML", 318000, "Hombre"),
    ("juleriaque", "j2", "3349668627530", "RABANNE", "Invictus Parfum 100 ml", 294480, "/Fragancias/Premium/Masculinas/Parfum/"),
    ("rouge", "r2", "3349668627530", "Rabanne", "Invictus Parfum 100 ml", 368100, "/Perfumes de hombre/"),
    ("juleriaque", "j3", "3349666007921", "RABANNE", "One Million EDT 100 ml", 320750, "/Fragancias/Premium/Masculinas/Eau de Toilette/"),
    ("rouge", "r3", "3349666007921", "Rabanne", "One Million EDT 100 ml", 224525, "/Perfumes de hombre/"),
    ("parfumerie", "p3", "", "RABANNE", "ONE MILLION EDT 100ML", 315000, "Hombre"),
    ("rouge", "r4", "3614274114645", "Yves Saint Laurent", "Myslf Le Parfum 100 ml", 479000, "/Perfumes de hombre/"),
    ("juleriaque", "j4", "3614274114645", "YVES SAINT LAURENT", "MYSLF Le Parfum 100 ml", 471000, "/Fragancias/Premium/Masculinas/Parfum/"),
    ("farmacity", "f1", "7798127370924", "Cher", "EDP Cher Dieciocho x 100 ml", 51990, "/Perfumes Y Fragancias/Mujeres/Perfumes/"),
    ("parfumerie", "p5", "", "CHER", "CHER DIECIOCHO EDP 100ML", 58500, "Mujer"),
    ("farmacity", "f2", "8411061081150", "Banderas", "EDT Banderas Blue Seduction x 100 ml", 41000, "/Perfumes Y Fragancias/Hombres/"),
    ("juleriaque", "j6", "8411061081150", "ANTONIO BANDERAS", "Blue Seduction EDT 100 ml", 44900, "/Fragancias/Low Cost/Masculinas/Eau de Toilette/"),
    ("parfumerie", "p6", "", "ANTONIO BANDERAS", "BLUE SEDUCTION MEN EDT 100ML", 43500, "Hombre"),
    ("parfumerie", "p7", "", "CALVIN KLEIN", "GREEN TEA EDT 100ML", 51900, "Mujer"),
    ("farmacity", "f3", "7798460730546", "Cher", "Body Splash Cher Onyx x 135 ml", 21990, "/Perfumes Y Fragancias/Mujeres/Colonias Y Body Splash/"),
    ("rouge", "r8", "P65055742KIT11", "Rabanne", "Invictus EDT 100 ml + Invictus Backpack KITG", 320750, "/Perfumes de hombre/"),
    ("farmacity", "f9", "7791600079277", "Valeria Mazza", "Desodorante Valeria Velvet By Valeria Mazza x 123 ml", 6195, "/Desodorantes/"),
]


def raw(store, sku, ean, brand, name, price, hint, in_stock=True):
    return {"sku": sku, "ean": ean, "brand": brand, "name": name, "url": config.STORES[store]["base"],
            "image": "", "price": price, "list_price": price * 1.2, "in_stock": in_stock,
            "gender_hint": hint, "hint": hint}


def main(out="demo", days=45, today=None):
    random.seed(7)
    today = today or date.today()
    Path(out).mkdir(exist_ok=True)
    dbp = Path(out) / "prices.db"
    dbp.unlink(missing_ok=True)
    con = db.connect(dbp)
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        by_store = {}
        for it in ITEMS:
            price = it[5]
            if i > 30:
                price = round(price * 0.94)       # hace un mes costaba menos (inflación)
            if it[1] == "j2" and i <= 2:
                price = round(price * 0.72)       # baja fuerte reciente -> oportunidad histórica
            if it[1] == "p3" and i > 10:
                continue                          # aparece hace 10 días
            by_store.setdefault(it[0], []).append(raw(*it[:5], price, it[6]))
        for store, raws in by_store.items():
            db.save_store(con, store, d.isoformat(), [(r, normalize.parse(r)) for r in raws],
                          config.MIN_COVERAGE)
    stats = build.build(con, Path(out) / "public", today)
    print("DEMO generada:", stats)
    return con, stats


if __name__ == "__main__":
    main()
