"""
SKU Collision Inspector v1.0
Interactive dashboard for the Haven SKU hygiene initiative (agreed w/ Lisa 5/28).

ATOMIC UNIT = Product ID. Product ID is unique across all of Blaze and carries
the shop-specific context where the SKU actually lives and gets fixed. We do NOT
collapse to Master/Company Product ID: a single Master Product ID can legitimately
carry different SKUs across shops (e.g. METRC tags entered as SKUs), so collapsing
on it both hides real variation and mis-groups. (Per Charles, 5/29.)

Three collision lenses against the Blaze company exports:
  TYPE 1  one SKU worn by 2+ products with DIFFERENT names ("different products,
          same SKU"). Discriminator = item name / brand, judged with shop context.
  TYPE 2  a product SKU whose string equals a batch code ("product SKU == batch SKU").
  TYPE 3  one Master Product ID whose SKU varies across its shops (unstable SKU).

Reads the two Blaze COMPANY exports directly from disk (no 130MB re-upload):
  *COMPANY_PRODUCTS_EXPORT*.csv      (per-shop product rows; Product ID = row key)
  *COMPANY_PRODUCT_BATCH_EXPORT*.csv (per-batch rows)

CHANGELOG:
v1.0 (2026-05-29) - Initial build. Product-ID-anchored. Type 1/2/3 + browse.
v1.1 (2026-06-01) - Shop / brand / in-stock filters on the Type 2 (batch-ID-in-SKU)
                    view, per the Forced Scanning and SKU Integrity call.
"""

import glob
import io
import os
import re

import pandas as pd
import streamlit as st

# ============================================================================
# CONFIGURATION
# ============================================================================

VERSION = "1.1.0"
DEFAULT_DATA_DIR = r"C:\Users\Charles\archangels\_Working Files"
PRODUCTS_GLOB = "*COMPANY_PRODUCTS_EXPORT*.csv"
BATCH_GLOB = "*COMPANY_PRODUCT_BATCH_EXPORT*.csv"

TEAL, GOLD, MAGENTA = "#3DC0CC", "#FFCA45", "#9E1F63"  # Haven branding
BLAZE_PREFIX = "https://retail.blaze.me/inventory/product/"  # + Product ID

PROD_COLS = ["Shop", "SKU", "Item", "Category", "Cannabis", "Brand", "Cannabis Type",
             "Active", "Available Online", "Inventory Available", "Vendor",
             "Product ID", "Master Product ID", "Company Product ID"]
BATCH_COLS = ["Shop Name", "Product ID", "Product Name", "Product SKU", "Batch ID",
              "Status", "Archived?", "Brand", "Category", "Current Qty",
              "Metrc Package Label"]

BLANK_TOKENS = {"", "N/A", "n/a", "NA", "None", "nan", "NaN"}
METRC_RE = re.compile(r"^1A4[0-9A-Fa-f]{18,}$")  # METRC package tag shape

st.set_page_config(page_title=f"SKU Collision Inspector v{VERSION}",
                   page_icon="🔍", layout="wide")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_blank(series: pd.Series) -> pd.Series:
    return series.fillna("").str.strip().isin(BLANK_TOKENS)


def norm(series: pd.Series) -> pd.Series:
    """Strip + collapse internal whitespace."""
    return series.fillna("").str.strip().str.replace(r"\s+", " ", regex=True)


def latest_match(data_dir: str, pattern: str):
    hits = glob.glob(os.path.join(data_dir, pattern))
    return max(hits, key=os.path.getmtime) if hits else None


def resolve_default_dir() -> str:
    """Local export folder if it exists, else a writable ./data dir (hosted/Cloud)."""
    if os.path.isdir(DEFAULT_DATA_DIR):
        return DEFAULT_DATA_DIR
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(local, exist_ok=True)
    return local


def looks_like_metrc(value: str) -> bool:
    return bool(METRC_RE.match(str(value).strip()))


def short_shop(s: pd.Series) -> pd.Series:
    return s.str.replace("HAVEN - ", "", regex=False)


# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(show_spinner=False)
def load_products(path: str, mtime: float) -> pd.DataFrame:
    """Per-shop products export, skipping the title banner. Product ID = row key."""
    df = pd.read_csv(path, skiprows=1, usecols=lambda c: c in PROD_COLS,
                     dtype=str, low_memory=False, keep_default_na=False)
    df["SKU"] = df["SKU"].fillna("").str.strip()
    df["nname"] = norm(df["Item"]).str.lower()      # different-product discriminator
    df["nbrand"] = norm(df["Brand"]).str.lower()
    df["is_active"] = df["Active"].str.lower().isin(["true", "yes"])
    df["inv_num"] = pd.to_numeric(df["Inventory Available"], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def load_batches(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=1, usecols=lambda c: c in BATCH_COLS,
                     dtype=str, low_memory=False, keep_default_na=False)
    df["Product SKU"] = df["Product SKU"].fillna("").str.strip()
    df["Batch ID"] = df["Batch ID"].fillna("").str.strip()
    return df


# ============================================================================
# COLLISION COMPUTATION
# ============================================================================

@st.cache_data(show_spinner=False)
def compute_type1(_prod: pd.DataFrame, sig: str) -> pd.DataFrame:
    """SKUs worn by 2+ products with different names (genuine collisions)."""
    prod = _prod
    d = prod[~is_blank(prod["SKU"])].copy()
    d["pkey"] = d["nname"] + "||" + d["nbrand"]   # product identity = (name, brand)
    rows = []
    for sku, g in d.groupby("SKU"):
        n_prod = g["pkey"].nunique()
        if n_prod < 2:                      # same product across shops = not a collision
            continue
        n_name, n_brand = g["nname"].nunique(), g["nbrand"].nunique()
        names = sorted(set(norm(g["Item"])))
        rows.append({
            "SKU": sku,
            "Severity": "Multi-brand" if n_brand > 1 else "Multi-name",
            "# products": n_prod,
            "# brands": n_brand,
            "# Product IDs": g["Product ID"].nunique(),
            "# shops": g["Shop"].nunique(),
            "Cannabis": "/".join(sorted(set(g["Cannabis"]) - {""})),
            "Brands": " | ".join(sorted(set(norm(g["Brand"])) - {""}))[:90],
            "Categories": " | ".join(sorted(set(g["Category"]) - {""}))[:60],
            "Product names": " || ".join(names)[:240],
            "_brands": sorted(set(norm(g["Brand"])) - {""}),
            "_cats": sorted(set(g["Category"]) - {""}),
            "_cannabis": sorted(set(g["Cannabis"]) - {""}),
            "_shops": sorted(set(g["Shop"]) - {""}),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_sev"] = out["Severity"].map({"Multi-brand": 0, "Multi-name": 1})
    return out.sort_values(["_sev", "# products", "# Product IDs"],
                           ascending=[True, False, False]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def compute_type2(_prod: pd.DataFrame, _batch: pd.DataFrame, sig: str) -> pd.DataFrame:
    """Products whose SKU is an exact 1:1 match to a Batch ID (batch code in SKU field).

    One row per shop-level product, so each can be opened in Blaze and fixed.
    'Same product?' = yes when the SKU is the product's own batch number.
    """
    prod, batch = _prod, _batch
    bid = batch[~is_blank(batch["Batch ID"])].copy()
    bid["pn"] = norm(bid["Product Name"])
    grp = bid.groupby("Batch ID")
    disp = grp["pn"].apply(lambda s: " || ".join(sorted(set(s)))[:90]).to_dict()
    low = grp["pn"].apply(lambda s: set(s.str.lower())).to_dict()
    stat = grp["Status"].apply(lambda s: "/".join(sorted(set(s) - {""}))).to_dict()

    hits = prod[(~is_blank(prod["SKU"])) & (prod["SKU"].isin(low.keys()))].copy()
    if hits.empty:
        return pd.DataFrame()
    hits["Shop"] = short_shop(hits["Shop"])
    rows = []
    for _, r in hits.iterrows():
        sku = r["SKU"]
        rows.append({
            "Product": r["Item"],
            "Brand": r["Brand"],
            "Shop": r["Shop"],
            "SKU (is a Batch ID)": sku,
            "Active": r["Active"],
            "Inventory": r["Inventory Available"],
            "Same product?": "yes" if r["nname"] in low.get(sku, set()) else "no",
            "Batch belongs to": disp.get(sku, ""),
            "Batch status": stat.get(sku, ""),
            "Blaze": BLAZE_PREFIX + r["Product ID"],
        })
    return pd.DataFrame(rows).sort_values(["Product", "Shop"]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def compute_type3(_prod: pd.DataFrame, sig: str) -> pd.DataFrame:
    """Master Product IDs whose SKU varies across shops (unstable SKU)."""
    prod = _prod
    d = prod[(~is_blank(prod["SKU"])) & (~is_blank(prod["Master Product ID"]))]
    rows = []
    for mpid, g in d.groupby("Master Product ID"):
        skus = sorted(set(g["SKU"]))
        if len(skus) < 2:
            continue
        all_metrc = all(looks_like_metrc(s) for s in skus)
        rows.append({
            "Master Product ID": mpid,
            "Product": norm(g["Item"]).mode().iat[0] if len(g) else "",
            "Brand": norm(g["Brand"]).mode().iat[0] if len(g) else "",
            "# distinct SKUs": len(skus),
            "# shops": g["Shop"].nunique(),
            "All SKUs METRC-shaped": "⚠️ yes" if all_metrc else "",
            "Cannabis": "/".join(sorted(set(g["Cannabis"]) - {""})),
            "SKUs": " | ".join(skus[:6]) + (" …" if len(skus) > 6 else ""),
            "_cannabis": sorted(set(g["Cannabis"]) - {""}),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["All SKUs METRC-shaped", "# distinct SKUs"],
                              ascending=[False, False]).reset_index(drop=True)
    return out


def product_detail(prod: pd.DataFrame, sku: str) -> pd.DataFrame:
    """Every Product ID (shop-level) wearing a SKU — the remediation view."""
    g = prod[prod["SKU"] == sku].copy()
    g["Shop"] = short_shop(g["Shop"])
    g["Blaze"] = BLAZE_PREFIX + g["Product ID"]
    g["Orphan"] = is_blank(g["Master Product ID"]).map({True: "⚠️ orphan", False: ""})
    out = g[["Item", "Brand", "Category", "Cannabis", "Shop", "Active",
             "Inventory Available", "Orphan", "Product ID", "Blaze"]].rename(
        columns={"Item": "Product", "Inventory Available": "Inventory"})
    return out.sort_values(["Product", "Shop"]).reset_index(drop=True)


def master_detail(prod: pd.DataFrame, mpid: str) -> pd.DataFrame:
    g = prod[prod["Master Product ID"] == mpid].copy()
    g["Shop"] = short_shop(g["Shop"])
    g["Blaze"] = BLAZE_PREFIX + g["Product ID"]
    return (g[["Shop", "Item", "SKU", "Active", "Inventory Available", "Product ID", "Blaze"]]
            .rename(columns={"Item": "Product", "Inventory Available": "Inventory"})
            .sort_values("Shop").reset_index(drop=True))


# ============================================================================
# UI HELPERS
# ============================================================================

def df_download(df: pd.DataFrame, label: str, fname: str):
    buf = io.StringIO()
    df.drop(columns=[c for c in df.columns if c.startswith("_")],
            errors="ignore").to_csv(buf, index=False)
    st.download_button(label, buf.getvalue(), fname, "text/csv")


def show_detail(df: pd.DataFrame):
    """Render a per-product detail table with a clickable Blaze link column."""
    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "Product": st.column_config.TextColumn(width="large"),
        "Blaze": st.column_config.LinkColumn("Blaze", display_text="open ↗")})


def selected_row(event):
    rows = event.selection.rows if hasattr(event, "selection") else []
    return rows[0] if rows else None


def apply_t1_filters(t1, cannabis, brands, cats, shops, severity, min_prod):
    if t1.empty:
        return t1
    m = pd.Series(True, index=t1.index)
    if severity != "All":
        m &= t1["Severity"] == severity
    if cannabis != "All":
        m &= t1["_cannabis"].apply(lambda s: cannabis in s)
    if brands:
        bs = set(brands)
        m &= t1["_brands"].apply(lambda s: bool(bs & set(s)))
    if cats:
        cs = set(cats)
        m &= t1["_cats"].apply(lambda s: bool(cs & set(s)))
    if shops:
        ss = set(shops)
        m &= t1["_shops"].apply(lambda s: bool(ss & set(s)))
    m &= t1["# products"] >= min_prod
    return t1[m]


# ============================================================================
# MAIN
# ============================================================================

def main():
    st.markdown(
        f"<h1 style='margin-bottom:0'>🔍 SKU Collision Inspector "
        f"<span style='color:{TEAL}'>v{VERSION}</span></h1>"
        f"<p style='color:gray;margin-top:4px'>Anchored on <b>Product ID</b> "
        f"(shop-level, unique across Blaze). Surfaces different products sharing a "
        f"SKU, batch codes sitting in SKU fields, and SKUs that drift within one "
        f"master product.</p>", unsafe_allow_html=True)

    # ---- sidebar: data source ----
    st.sidebar.header("📄 Data Source")
    data_dir = st.sidebar.text_input("Export folder", resolve_default_dir())

    # Uploads are saved into the export folder so the newest matching export is used.
    # Local: persists across restarts. Hosted (Cloud): the filesystem is per-session.
    with st.sidebar.expander("⬆️ Upload exports", expanded=False):
        st.caption("Re-export from Blaze and drop the files here. They're saved into "
                   "the export folder and used immediately. On a hosted deployment the "
                   "filesystem is per-session, so re-upload after the app restarts.")
        uploaders = [("Products", st.file_uploader("Products export CSV", type="csv", key="up_prod")),
                     ("Batches", st.file_uploader("Batch export CSV", type="csv", key="up_batch"))]
        saved = []
        for label, up in uploaders:
            if up is not None:
                s = (up.name, getattr(up, "size", None))
                if st.session_state.get(f"saved_{label}") != s:
                    os.makedirs(data_dir, exist_ok=True)
                    with open(os.path.join(data_dir, up.name), "wb") as fh:
                        fh.write(up.getbuffer())
                    st.session_state[f"saved_{label}"] = s
                    saved.append(up.name)
        if saved:
            st.cache_data.clear()
            st.success("Saved: " + ", ".join(saved))
            st.rerun()

    prod_path = latest_match(data_dir, PRODUCTS_GLOB)
    batch_path = latest_match(data_dir, BATCH_GLOB)
    if not prod_path or not batch_path:
        missing = []
        if not prod_path:
            missing.append("Products export (`*COMPANY_PRODUCTS_EXPORT*.csv`)")
        if not batch_path:
            missing.append("Batch export (`*COMPANY_PRODUCT_BATCH_EXPORT*.csv`)")
        st.info("### ⬆️ Upload the Blaze company exports to begin\n\n"
                "Use **Upload exports** in the sidebar. Still needed: "
                + "; ".join(missing) + ".")
        st.stop()
    st.sidebar.caption(f"**Products:** {os.path.basename(prod_path)}")
    st.sidebar.caption(f"**Batches:** {os.path.basename(batch_path)}")
    st.sidebar.subheader("Filters")
    include_inactive = st.sidebar.toggle("Include inactive products", value=False,
        help="Off (default) = active products only.")
    inv_only = st.sidebar.toggle("With available inventory only", value=False,
        help="Keep only shop rows with Inventory Available > 0.")
    hide_orphans = st.sidebar.toggle("Hide orphans (no Master Product ID)", value=True,
        help="Orphan = product with no Master Product ID; usually needs inactivating.")
    if st.sidebar.button("🔄 Reload data (clear cache)"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Loading exports (first load parses ~130MB)..."):
        full_prod = load_products(prod_path, os.path.getmtime(prod_path))
        batch = load_batches(batch_path, os.path.getmtime(batch_path))
        prod = full_prod
        if not include_inactive:
            prod = prod[prod["is_active"]]
        if inv_only:
            prod = prod[prod["inv_num"] > 0]
        if hide_orphans:
            prod = prod[~is_blank(prod["Master Product ID"])]
        prod = prod.copy()
        sig = (f"{os.path.getmtime(prod_path)}|inact={include_inactive}"
               f"|inv={inv_only}|orph={hide_orphans}")
        sigb = f"{os.path.getmtime(batch_path)}"
        t1 = compute_type1(prod, sig)
        t2 = compute_type2(prod, batch, sig + sigb)
        t3 = compute_type3(prod, sig)

    # ---- top metrics ----
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Product IDs", f"{len(prod):,}")
    c2.metric("Distinct SKUs", f"{prod.loc[~is_blank(prod['SKU']), 'SKU'].nunique():,}")
    nb = int((t1["Severity"] == "Multi-brand").sum()) if not t1.empty else 0
    c3.metric("① Same SKU, diff product", f"{len(t1):,}", f"{nb} multi-brand")
    nsku2 = t2["SKU (is a Batch ID)"].nunique() if not t2.empty else 0
    c4.metric("② Batch ID in SKU field", f"{len(t2):,}", f"{nsku2} distinct SKUs")
    n3 = int((t3["All SKUs METRC-shaped"] != "").sum()) if not t3.empty else 0
    c5.metric("③ SKU varies in master", f"{len(t3):,}", f"{n3} all-METRC")
    flags = ["inactive included" if include_inactive else "🟢 active only"]
    if inv_only:
        flags.append("in-stock only")
    if hide_orphans:
        flags.append("orphans hidden")
    st.caption(" · ".join(flags) + f" · {len(prod):,} product rows in view")

    tabs = st.tabs(["① Same SKU → diff products", "② Batch ID in SKU field",
                    "③ SKU drift within master", "🔎 Browse / search", "ℹ️ Methodology"])

    # ---------------- TAB 1 ----------------
    with tabs[0]:
        st.subheader("Different products sharing one SKU")
        st.caption("A SKU worn by 2+ products with **different names**. "
                   "**Multi-brand** = different brands on one SKU (fix first). "
                   "**Multi-name** = same brand, different products "
                   "(e.g. Ice Goddess vs Ice Queen on `850003551708`). "
                   "Same product across shops is *not* counted here.")

        f1, f2, f3 = st.columns([1, 1, 2])
        severity = f1.selectbox("Severity", ["All", "Multi-brand", "Multi-name"])
        cannabis = f2.selectbox("Cannabis", ["All", "Yes", "No"])
        min_prod = f3.slider("Min distinct products per SKU", 2, 9, 2)
        all_brands = sorted({b for s in t1["_brands"] for b in s}) if not t1.empty else []
        all_cats = sorted({c for s in t1["_cats"] for c in s}) if not t1.empty else []
        all_shops = sorted({short_shop(pd.Series([s]))[0]
                            for ss in t1["_shops"] for s in ss}) if not t1.empty else []
        g1, g2, g3 = st.columns(3)
        brands = g1.multiselect("Brand", all_brands)
        cats = g2.multiselect("Category", all_cats)
        shops_sel = g3.multiselect("Shop", all_shops)
        shops_full = [f"HAVEN - {s}" for s in shops_sel]

        view = apply_t1_filters(t1, cannabis, brands, cats, shops_full, severity, min_prod)
        st.markdown(f"**{len(view):,}** of {len(t1):,} colliding SKUs match.")
        cols = ["SKU", "Product names", "Severity", "# products", "# brands",
                "# Product IDs", "# shops", "Cannabis", "Brands", "Categories"]
        ev = st.dataframe(view[cols], use_container_width=True, hide_index=True,
                          height=360, on_select="rerun", selection_mode="single-row",
                          column_config={"Product names": st.column_config.TextColumn(width="large")})
        df_download(view, "📥 Download filtered Type-1 list", "sku_type1_collisions.csv")
        i = selected_row(ev)
        if i is not None:
            sku = view.iloc[i]["SKU"]
            st.markdown(f"#### Every Product ID wearing SKU `{sku}`  "
                        f"<span style='color:gray'>(fix at the shop level — click "
                        f"**open ↗** to edit in Blaze)</span>", unsafe_allow_html=True)
            show_detail(product_detail(prod, sku))
        else:
            st.info("Select a row to see every shop-level Product ID on that SKU.")

    # ---------------- TAB 2 ----------------
    with tabs[1]:
        st.subheader("Products with a Batch ID sitting in the SKU field")
        st.markdown(
            "Each product below has a **batch code** in its **SKU** field — its SKU "
            "exactly matches a `Batch ID` from the batch export. A batch code changes "
            "every batch, so it breaks scanning, lookups, and reporting; the SKU "
            "should be a stable product identifier instead.\n\n"
            "**Fix:** click **open ↗** to edit the product in Blaze and replace the "
            "SKU. *Same product? = yes* means the SKU is the product's own batch "
            "number; *no* means it points at a different product's batch.")
        if t2.empty:
            st.success("No products have a Batch ID in their SKU field. 🎉")
        else:
            bf1, bf2, bf3 = st.columns([1, 1, 1])
            t2_shops = sorted(s for s in t2["Shop"].unique() if s)
            t2_brands = sorted(b for b in t2["Brand"].unique() if b)
            sel_shops2 = bf1.multiselect("Shop", t2_shops, key="t2_shop")
            sel_brands2 = bf2.multiselect("Brand", t2_brands, key="t2_brand")
            instock2 = bf3.toggle("In-stock only", value=False, key="t2_inv",
                                  help="Keep only rows with Inventory > 0 (what's "
                                       "ready to sell now).")
            view2 = t2
            if sel_shops2:
                view2 = view2[view2["Shop"].isin(sel_shops2)]
            if sel_brands2:
                view2 = view2[view2["Brand"].isin(sel_brands2)]
            if instock2:
                view2 = view2[pd.to_numeric(view2["Inventory"], errors="coerce").fillna(0) > 0]
            cols2 = ["Product", "Brand", "Shop", "SKU (is a Batch ID)", "Active",
                     "Inventory", "Same product?", "Batch belongs to", "Batch status",
                     "Blaze"]
            st.markdown(f"**{len(view2):,}** of {len(t2):,} product rows · "
                        f"**{view2['SKU (is a Batch ID)'].nunique():,}** distinct SKUs.")
            st.dataframe(view2[cols2], use_container_width=True, hide_index=True, height=460,
                column_config={
                    "Product": st.column_config.TextColumn(width="medium"),
                    "Blaze": st.column_config.LinkColumn("Blaze", display_text="open ↗")})
            df_download(view2, "📥 Download list", "sku_batch_id_in_sku.csv")

    # ---------------- TAB 3 ----------------
    with tabs[2]:
        st.subheader("SKU drift within a single Master Product ID")
        st.caption("One master product carrying **different SKUs across its shops**. "
                   "When every SKU is METRC-shaped, the shop instances are using "
                   "METRC package tags as SKUs instead of a stable product SKU "
                   "(this is exactly why Master Product ID is *not* a safe collapse key).")
        if t3.empty:
            st.success("No master products with drifting SKUs.")
        else:
            a, b = st.columns([1, 1])
            metrc3 = a.toggle("All-SKUs-METRC only", value=False, key="m3")
            can3 = b.selectbox("Cannabis", ["All", "Yes", "No"], key="c3")
            v3 = t3.copy()
            if metrc3:
                v3 = v3[v3["All SKUs METRC-shaped"] != ""]
            if can3 != "All":
                v3 = v3[v3["_cannabis"].apply(lambda s: can3 in s)]
            st.markdown(f"**{len(v3):,}** of {len(t3):,} master products match.")
            shw = ["Master Product ID", "Product", "Brand", "# distinct SKUs", "# shops",
                   "All SKUs METRC-shaped", "Cannabis", "SKUs"]
            ev3 = st.dataframe(v3[shw], use_container_width=True, hide_index=True,
                               height=340, on_select="rerun", selection_mode="single-row")
            df_download(v3, "📥 Download Type-3 list", "sku_type3_master_drift.csv")
            i3 = selected_row(ev3)
            if i3 is not None:
                mpid = v3.iloc[i3]["Master Product ID"]
                st.markdown(f"#### Per-shop SKUs for master `{mpid}`")
                show_detail(master_detail(prod, mpid))

    # ---------------- TAB 4 ----------------
    with tabs[3]:
        st.subheader("Look up any SKU")
        q = st.text_input("Enter a SKU (exact match)").strip()
        if q:
            p = prod[prod["SKU"] == q]
            if p.empty:
                st.warning("No product rows with that SKU.")
            else:
                st.markdown(f"**{p['nname'].nunique()}** distinct product name(s) across "
                            f"**{p['Product ID'].nunique()}** Product IDs / "
                            f"**{p['Shop'].nunique()}** shops.")
                show_detail(product_detail(prod, q))
            b = batch[(batch["Product SKU"] == q) | (batch["Batch ID"] == q)]
            if not b.empty:
                st.markdown(f"#### Batches referencing `{q}`")
                st.dataframe(b[["Shop Name", "Product Name", "Product SKU", "Batch ID",
                                "Status", "Current Qty", "Metrc Package Label"]],
                             use_container_width=True, hide_index=True)

    # ---------------- TAB 5 ----------------
    with tabs[4]:
        st.markdown(f"""
### How collisions are defined

**Source files** (auto-detected, newest in the export folder):
- `{os.path.basename(prod_path)}`
- `{os.path.basename(batch_path)}`

**Atomic unit = `Product ID`.** It is unique per row (shop-level) and unique
across all of Blaze; it carries the shop context where a SKU lives and is fixed.
We **do not** collapse to `Master Product ID` — a single master product can
legitimately carry different SKUs across shops (often METRC tags entered as
SKUs), so collapsing on it hides variation and mis-groups (see Type 3).

**① Same SKU → different products.** A SKU worn by Product IDs with **2+ distinct
item names**. Same item name across shops = same product in many stores, **not**
a collision. *Multi-brand* (different brands on one SKU) is highest severity;
*Multi-name* is same brand / different product (Ice Goddess vs Ice Queen).

**② Batch ID in the SKU field.** Products whose SKU is an exact 1:1 match to a
`Batch ID` from the batch export — a batch code sitting in the SKU field instead of
a stable product SKU. Listed per shop-level product so each can be fixed in Blaze.
Per-view filters (shop, brand, in-stock) narrow to what a single store or vendor
owner is working right now.

**③ SKU drift within a master.** One `Master Product ID` whose Product IDs carry
2+ distinct SKUs across shops. "All SKUs METRC-shaped" flags the tag-as-SKU pattern.

**Filters** match a SKU if **any** of its products matches (a cannabis filter
surfaces every collision *involving* a cannabis product); the detail view always
shows all entangled Product IDs.

**Filters (sidebar), applied before collisions are computed.** *Active only*
(default) drops inactive products. *With available inventory only* keeps shop rows
with Inventory Available > 0. *Hide orphans* (default) drops products with no
`Master Product ID` — orphans that usually need inactivating (e.g. stray
baby-Jeeter profiles).

**Refreshing data.** Drop new Blaze exports into the export folder, or upload them
in the sidebar. Uploads are saved into that folder, so the dataset persists on
disk and survives restarts; the newest matching export is always used. Hit
*Reload data* after dropping files in directly.

*Detail tables link to Blaze (`retail.blaze.me/inventory/product/<id>`) — click
**open ↗** to edit a product directly.*
""")

    st.sidebar.markdown("---")
    with st.sidebar.expander("📋 Changelog"):
        st.markdown("**v1.1.0** (2026-06-01)\n- Shop / brand / in-stock filters on "
                    "the ② Batch-ID-in-SKU view.\n\n"
                    "**v1.0.0** (2026-05-29)\n- Product-ID-anchored build: "
                    "Type 1 (diff products / same SKU), Type 2 (SKU = batch code), "
                    "Type 3 (SKU drift within master), browse + methodology.")
    st.sidebar.markdown(f"**Version {VERSION}**")


if __name__ == "__main__":
    main()
