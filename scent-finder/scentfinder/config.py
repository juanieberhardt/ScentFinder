"""Configuración: tiendas y parámetros del algoritmo de oportunidades."""

STORES = {
    "juleriaque": {
        "name": "Juleriaque",
        "platform": "vtex",
        "base": "https://www.juleriaque.com.ar",
        "categories": [100000001],  # Fragancias
    },
    "rouge": {
        "name": "Rouge",
        "platform": "vtex",
        "base": "https://www.perfumeriasrouge.com",
        "categories": [100],  # Perfumes y fragancias
    },
    "farmacity": {
        "name": "Farmacity",
        "platform": "vtex",
        "base": "https://www.farmacity.com",
        "categories": [80],  # Perfumes Y Fragancias
    },
    "parfumerie": {
        "name": "Parfumerie",
        "platform": "magento",
        "base": "https://www.parfumerie.com.ar",
        "categories": [975, 250],  # PERFUMES, PERFUMES XXL
        "brand_attr": "mgs_brand",
        "gender_attr": "gender_product",
    },
}

# --- Scraping ---
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
REQUEST_DELAY = 0.35      # segundos entre requests (ser amable con las tiendas)
REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
# Si una tienda devuelve menos de esta fracción de lo que tenía ayer, se asume
# scrape incompleto y NO se marcan como "sin stock" los productos que faltan.
MIN_COVERAGE = 0.6

# --- Oportunidades ---
MARKET_GAP_MIN = 0.12     # 12% más barato que la mediana de las otras tiendas
HIST_DROP_MIN = 0.12      # 12% por debajo de su precio habitual
HIST_WINDOW_DAYS = 60     # ventana para el "precio habitual" (mediana diaria)
HIST_MIN_DAYS = 14        # días de historial mínimos para evaluar la baja
ATL_MIN_DAYS = 30         # días de historial mínimos para "mínimo histórico"
SUSPICIOUS_GAP = 0.60     # diferencias mayores se marcan "verificar"
