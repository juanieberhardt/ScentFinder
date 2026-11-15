"""python -m unittest discover tests"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scentfinder import demo, match, normalize, opportunities, scrapers


def P(name, brand="X", ean="", hint=""):
    return normalize.parse({"name": name, "brand": brand, "ean": ean, "gender_hint": hint, "hint": hint})


class Normalize(unittest.TestCase):
    def test_fields(self):
        n = P("Invictus EDT 100 ml", "RABANNE", "3349668515660", "/Fragancias/Masculinas/")
        self.assertEqual((n["conc"], n["ml"], n["gender"], n["kind"]), ("EDT", 100, "M", "perfume"))
        self.assertEqual(n["key"], "invictus|EDT|100")

    def test_same_key_across_store_formats(self):
        a = P("EDP Cher Dieciocho x 100 ml", "Cher")
        b = P("CHER DIECIOCHO EDP 100ML", "CHER")
        self.assertEqual(a["key"], b["key"])
        self.assertEqual(P("Blue Seduction EDT 100 ml", "ANTONIO BANDERAS")["key"],
                         P("EDT Banderas Blue Seduction x 100 ml", "Banderas")["key"])

    def test_sizes_and_concentrations_differ(self):
        self.assertNotEqual(P("Invictus EDT 100 ml")["key"], P("Invictus EDT 50 ml")["key"])
        self.assertNotEqual(P("Invictus EDT 100 ml")["key"], P("Invictus Parfum 100 ml")["key"])

    def test_kinds(self):
        self.assertEqual(P("Invictus EDT 100 ml + Deo 150 ml")["kind"], "set")
        self.assertEqual(P("Invictus EDT 100 ml + Deo 150 ml")["key"], "")
        self.assertEqual(P("Desodorante Valeria Velvet x 123 ml")["kind"], "other")
        self.assertEqual(P("Body Splash Cher Onyx x 135 ml")["kind"], "body")

    def test_ean(self):
        self.assertEqual(normalize.norm_ean("3349668614530P"), "3349668614530")
        self.assertEqual(normalize.norm_ean("P65165373KIT5"), "")
        self.assertEqual(normalize.norm_ean("085715166708"), "85715166708")


def O(i, store, name, brand, ean="", hint=""):
    return {"id": i, "store": store, "sku": str(i), **P(name, brand, ean, hint)}


class Match(unittest.TestCase):
    def test_ean_and_name(self):
        offers = [
            O(1, "jul", "Invictus EDT 100 ml", "RABANNE", "3349668515660"),
            O(2, "rouge", "Invictus EDT 100 ml", "Paco Rabanne", "3349668515660"),
            O(3, "parf", "INVICTUS EDT 100ML", "RABANNE"),
            O(4, "parf", "INVICTUS EDT 50ML", "RABANNE"),
        ]
        groups = sorted(match.group(offers), key=lambda g: -len(g["offers"]))
        self.assertEqual({o["id"] for o in groups[0]["offers"]}, {1, 2, 3})
        self.assertEqual(groups[0]["match"], "nombre")
        self.assertEqual(len(groups), 2)

    def test_gender_conflict_not_merged(self):
        offers = [
            O(1, "a", "100% Passion Men EDP 100 ml", "AF"),
            O(2, "b", "100% Passion Woman EDP 100 ml", "AF"),
            O(3, "c", "100% Passion EDP 100 ml", "AF"),
        ]
        self.assertEqual(len(match.group(offers)), 3)

    def test_stable_id(self):
        o = [O(1, "a", "Invictus EDT 100 ml", "R", "3349668515660")]
        self.assertEqual(match.group(o)[0]["id"], match.group(o)[0]["id"])


class Opp(unittest.TestCase):
    def test_market_gap(self):
        p = {"match": "ean", "offers": [
            {"id": 1, "store": "a", "price": 70, "in_stock": True},
            {"id": 2, "store": "b", "price": 100, "in_stock": True},
            {"id": 3, "store": "c", "price": 50, "in_stock": False}]}
        ev = opportunities.evaluate(p, {}, date(2026, 11, 15))
        self.assertEqual(ev["best_offer"], 1)
        self.assertAlmostEqual(ev["gap"], 0.3)
        self.assertTrue(ev["is_opp"])

    def test_hist_drop_and_atl(self):
        p = {"match": "single", "offers": [{"id": 1, "store": "a", "price": 80, "in_stock": True}]}
        h = {1: [("2026-09-01", 100, 1), ("2026-11-15", 80, 1)]}
        ev = opportunities.evaluate(p, h, date(2026, 11, 15))
        self.assertAlmostEqual(ev["drop"], 0.2)
        self.assertTrue(ev["atl"] and ev["is_opp"])

    def test_not_enough_history(self):
        p = {"match": "single", "offers": [{"id": 1, "store": "a", "price": 80, "in_stock": True}]}
        ev = opportunities.evaluate(p, {1: [("2026-11-10", 100, 1), ("2026-11-15", 80, 1)]}, date(2026, 11, 15))
        self.assertIsNone(ev["drop"])
        self.assertFalse(ev["is_opp"])

    def test_out_of_stock_days_ignored(self):
        rows = [("2026-11-01", 100, 1), ("2026-11-05", 100, 0), ("2026-11-10", 90, 1)]
        self.assertEqual(opportunities.daily_series(rows, date(2026, 11, 12), 60), [100] * 4 + [90] * 2)


class FakeResp:
    def __init__(self, data, total=None):
        self._d, self.headers = data, {"resources": f"0-0/{total}"} if total is not None else {}

    def json(self):
        return self._d


class Vtex(unittest.TestCase):
    def test_splits_big_categories(self):
        """Categoría con >2500: debe bajar a las subcategorías y paginar todo."""
        sizes = {"1": 3000, "1/2": 1800, "1/3": 1200}
        tree = [{"id": 1, "children": [{"id": 2, "children": []}, {"id": 3, "children": []}]}]

        def get(self, url, params=None):
            if "category/tree" in url:
                return FakeResp(tree)
            path = params["fq"][3:-1]
            if params["_to"] == 0:
                return FakeResp([], sizes[path])
            n = sizes[path]
            items = [{"productId": f"{path}-{i}", "brand": "B", "productName": "N", "link": "https://x",
                      "categories": ["/c/"], "items": [{"itemId": f"{path}-{i}", "ean": "", "nameComplete": "N EDT 100 ml",
                      "images": [], "sellers": [{"commertialOffer": {"Price": 10, "ListPrice": 12, "AvailableQuantity": 1}}]}]}
                     for i in range(params["_from"], min(params["_to"] + 1, n))]
            return FakeResp(items, n)

        with mock.patch.object(scrapers.Http, "get", get):
            out = scrapers.scrape_vtex({"base": "https://x", "categories": [1]}, log=lambda *_: None)
        self.assertEqual(len(out), 3000)
        self.assertTrue(all(o["in_stock"] for o in out))


class EndToEnd(unittest.TestCase):
    def test_demo_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            con, stats = demo.main(tmp, days=45, today=date(2026, 11, 15))
            data = json.loads((Path(tmp) / "public" / "data.json").read_text("utf-8"))
            con.close()
        by = {p["name"].lower(): p for p in data["products"]}
        one = next(p for p in data["products"] if "one million" in p["name"].lower())
        self.assertEqual(one["store"], "rouge")
        self.assertEqual(len(one["offers"]), 3)          # EAN (jul+rouge) + nombre (parfumerie)
        self.assertTrue(one["opp"] and one["gap"] > 0.25)
        inv = next(p for p in data["products"] if "invictus parfum" in p["name"].lower())
        self.assertTrue(inv["drop"] > 0.2 and inv["atl"])
        self.assertFalse(any("desodorante" in n for n in by))
        # historial guardado solo cuando cambia: pocas filas pese a 46 días
        self.assertLess(stats["products"], 20)


if __name__ == "__main__":
    unittest.main()
