# Scent Finder

Comparador de precios de perfumes en tiendas argentinas, con historial diario y
detección de oportunidades. Sin servidor: un job de GitHub Actions scrapea una
vez por día, guarda el historial en SQLite y publica una web estática en GitHub Pages.

## Tiendas

| Tienda     | Plataforma | Fuente de datos                           | EAN |
|------------|------------|-------------------------------------------|-----|
| Juleriaque | VTEX       | `/api/catalog_system/pub/products/search` | sí  |
| Rouge      | VTEX       | ídem                                      | sí  |
| Farmacity  | VTEX       | ídem                                      | sí  |
| Parfumerie | Magento 2  | `/graphql`                                | no  |

Se usan las APIs públicas de catálogo que consume el propio sitio de cada tienda
(no se parsea HTML). Para sumar otra tienda VTEX o Magento alcanza con agregarla
en `scentfinder/config.py` con su id de categoría de perfumes.

## Puesta en marcha

1. Crear un repo en GitHub y subir esta carpeta a `main`.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → "Scrape diario" → **Run workflow** (después corre solo todos los días 06:17 ARG).

La web queda en `https://<usuario>.github.io/<repo>/`.

Para probar local:

```bash
pip install -r requirements.txt
python -m unittest discover tests      # tests
python -m scentfinder.demo             # sitio con datos de ejemplo en demo/public
python -m scentfinder.run              # scrape real -> data/prices.db + public/
python -m http.server -d public 8000   # http://localhost:8000
```

## Cómo funciona

**Base de datos** (`data/prices.db`, guardada en la rama `data`):
`offers` (una fila por publicación de cada tienda) y `prices` (historial). El
scraper corre todos los días, pero solo escribe una fila cuando cambia el precio
o el stock; un día sin fila vale lo mismo que el anterior. Así un año de
historial ocupa pocos MB.

**Matching entre tiendas** (`match.py`):
1. Mismo código de barras (EAN) → mismo producto.
2. Si no hay EAN (Parfumerie): misma marca + mismos tokens de nombre + misma
   concentración + mismos ml. Los alias de marca se aprenden solos de los EAN
   compartidos. No se unen publicaciones con géneros distintos.
   En la web estos matches dicen "coincidencia por nombre".

**Oportunidades** (`opportunities.py`, umbrales en `config.py`):
- `gap`: cuánto más barata es la mejor oferta que la mediana de las otras tiendas.
- `drop`: cuánto bajó respecto de su precio habitual (mediana diaria de 60 días
  en esa tienda; necesita 14 días de historial).
- Mínimo histórico: precio más bajo registrado, alcanzado en los últimos 7 días.
- Es oportunidad si `gap ≥ 12%` o `drop ≥ 12%`. `score = 100·gap + 80·drop + 5`.
- El precio "de lista" tachado de las tiendas no se usa.

## Límites conocidos

- Las bajas vs. historial aparecen recién a los 14 días de correr.
- El precio es el publicado: no contempla descuentos por banco/tarjeta, cuotas ni envío.
- Si una tienda bloquea las IP de GitHub Actions, ese día queda sin datos (se
  avisa en la web) y las demás siguen. Alternativa: correr `scentfinder.run` en
  una PC/VPS en Argentina con cron.
- Revisar los términos de uso de cada tienda; el scraper hace ~3 requests/seg como máximo.
