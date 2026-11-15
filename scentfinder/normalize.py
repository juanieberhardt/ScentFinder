"""Normalización de nombres para poder matchear el mismo perfume entre tiendas.

De cada oferta se extrae: marca, concentración (EDP/EDT/...), ml, género, tipo
(perfume / body / set / otro) y una clave de nombre (tokens ordenados).
"""
import re
import unicodedata

BRAND_ALIASES = {
    "paco rabanne": "rabanne",
    "antonio banderas": "banderas",
    "ck": "calvin klein",
    "ysl": "yves saint laurent",
    "jpg": "jean paul gaultier",
    "giorgio armani": "armani",
    "emporio armani": "armani",
    "d g": "dolce gabbana",
    "ch": "carolina herrera",
    "polo ralph lauren": "ralph lauren",
    "christian dior": "dior",
    "hugo boss": "boss",
}

_CONC = [  # orden importa: lo más específico primero
    ("EXT", r"\b(extrait( de parfum)?|extracto)\b"),
    ("EDP", r"\b(eau de parfum|edp|edpi)\b"),
    ("EDT", r"\b(eau de toilette|edt)\b"),
    ("EDC", r"\b(eau de cologne|edc|colonia|cologne)\b"),
    ("BODY", r"\b(body (splash|mist|spray)|splash|hair mist)\b"),
    ("PARFUM", r"\b(le parfum|parfum)\b"),
]
_HINT_CONC = [
    ("EDP", "eau de parfum"), ("EDT", "eau de toilette"),
    ("EDC", "colonia"), ("BODY", "body splash"),
]
_OTHER = re.compile(
    r"\b(desodorante|deo|deodorant|antitranspirante|after shave|aftershave|"
    r"locion corporal|body lotion|body cream|crema|shower gel|gel de ducha|jabon|"
    r"shampoo|vela|difusor|home spray|aromatizador|balsamo|talco|leche corporal|"
    r"gift ?card|bolso solo|muestra)\b")
_SET = re.compile(r"\+|\b(set|kit|kitg|cofre|estuche|pack|combo|duo|trio)\b")
_MALE = re.compile(r"\b(men|man|homme|hombre|hombres|him|masculin[oa]s?|uomo|male|caballero)\b")
_FEMALE = re.compile(r"\b(women|woman|femme|mujer|mujeres|her|femenin[oa]s?|donna|female|dama)\b")
_ML = re.compile(r"(\d+(?:[.,]\d+)?)\s*ml\b")
_NOISE = {
    "x", "ml", "spray", "vaporizador", "vapo", "natural", "perfume", "fragancia",
    "promo", "for", "pour", "by", "de", "the", "edicion", "edition", "ed", "nuevo",
    "new", "recargable", "refillable",
}


def clean(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = t.lower().replace("&", " ")
    t = re.sub(r"[^a-z0-9+.,% ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def norm_brand(brand):
    b = re.sub(r"[^a-z0-9 ]+", " ", clean(brand))
    b = re.sub(r"\s+", " ", b).strip()
    return BRAND_ALIASES.get(b, b)


def norm_ean(ean):
    e = re.sub(r"[^0-9]", "", re.sub(r"[A-Za-z]+$", "", (ean or "").strip()))
    if (ean or "").strip()[:1].isalpha():  # códigos internos tipo "P65165373KIT5"
        return ""
    e = e.lstrip("0")
    return e if 8 <= len(e) <= 14 else ""


def gender_of(text):
    t = clean(text)
    m, f = bool(_MALE.search(t)), bool(_FEMALE.search(t))
    if "unisex" in t or (m and f):
        return ""
    return "M" if m else "F" if f else ""


def parse(raw):
    """raw offer -> campos normalizados."""
    name = clean(raw["name"])
    brand = norm_brand(raw.get("brand", ""))

    kind = "perfume"
    if _SET.search(name):
        kind = "set"
    elif _OTHER.search(name):
        kind = "other"

    conc = ""
    for code, rx in _CONC:
        if re.search(rx, name):
            conc = code
            break
    if not conc:
        hint = clean(raw.get("hint", ""))
        for code, word in _HINT_CONC:
            if word in hint:
                conc = code
                break
    if conc == "BODY" and kind == "perfume":
        kind = "body"

    mls = _ML.findall(name)
    ml = float(mls[0].replace(",", ".")) if mls else None

    gender = gender_of(raw.get("gender_hint", "")) or gender_of(name)

    # clave de nombre: sin marca, concentración, ml, género ni ruido
    t = name
    for _, rx in _CONC:
        t = re.sub(rx, " ", t)
    t = _ML.sub(" ", t)
    t = _MALE.sub(" ", t)
    t = _FEMALE.sub(" ", t)
    t = re.sub(r"[^a-z0-9% ]+", " ", t)
    brand_tokens = set(brand.split()) | set(clean(raw.get("brand", "")).split())
    tokens = sorted({w for w in t.split() if w not in _NOISE and w not in brand_tokens})

    key = ""
    if kind in ("perfume", "body") and ml and tokens and brand:
        key = f"{' '.join(tokens)}|{conc}|{ml:g}"

    return {
        "brand": brand, "conc": conc, "ml": ml, "gender": gender,
        "kind": kind, "key": key, "ean": norm_ean(raw.get("ean", "")),
    }
