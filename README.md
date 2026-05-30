# SKU Collision Inspector

Interactive Streamlit dashboard for the Haven SKU hygiene initiative. Inspects
collisions in Blaze SKUs across the chain.

## What it surfaces

Anchored on **Product ID** (unique per shop, unique across Blaze — it carries the
shop context where a SKU lives and gets fixed). It does **not** collapse to Master
Product ID, because a single master product can legitimately carry different SKUs
across shops (often METRC tags entered as SKUs).

1. **Same SKU → different products** — one SKU worn by 2+ products with different
   (name, brand). *Multi-brand* is highest severity; *Multi-name* = same brand,
   different product (e.g. High Gorgeous Ice Goddess vs Ice Queen).
2. **Batch ID in the SKU field** — a product whose SKU exactly equals a `Batch ID`
   (a batch code sitting in the SKU field instead of a stable product SKU).
3. **SKU drift within a master** — one Master Product ID whose SKU varies across shops.

## Inputs

Two Blaze **company** exports (auto-detected, newest in the export folder):

- `*COMPANY_PRODUCTS_EXPORT*.csv` — per-shop product rows
- `*COMPANY_PRODUCT_BATCH_EXPORT*.csv` — per-batch rows

Default export folder is set in `app.py` (`DEFAULT_DATA_DIR`); override it in the
sidebar. The first row of each export is a title banner (`skiprows=1`).

## Run locally

```powershell
# from this folder, using the archangels venv (has pandas; streamlit added 5/29)
& C:\Users\Charles\archangels\.venv\Scripts\python.exe -m streamlit run app.py
# then open http://localhost:8501
```

Click **🔄 Reload data** in the sidebar after dropping in fresh exports.

## Deploy to Streamlit Cloud

Main file: `app.py`. There are no local exports on Cloud, so the app opens on an
upload screen: use **Upload exports** in the sidebar and upload both Blaze company
CSVs. `maxUploadSize` is set to 300 MB in `.streamlit/config.toml`. The hosted
filesystem is per-session, so re-upload after the app restarts (durable hosting
would need cloud storage or a Google Sheet, a later step). The 130 MB products
export is large for the free tier; if it hits the memory ceiling, export a
single-shop file or fewer columns.

## Notes

- `explore*.py` / `test_logic.py` are throwaway validation scripts (gitignored).
- Product IDs deep-link to Blaze (`retail.blaze.me/inventory/product/<id>`) via the **open ↗** column.
