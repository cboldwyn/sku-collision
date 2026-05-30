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
2. **Product SKU = batch code** — a SKU string that equals a `Batch ID`. METRC-shaped
   values mean a METRC package tag was entered into the SKU field.
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

## Notes

- `explore*.py` / `test_logic.py` are throwaway validation scripts (gitignored).
- No Blaze deep-links yet; Product IDs shown as text.
