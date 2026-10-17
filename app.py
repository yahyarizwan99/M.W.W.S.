"""MWWS — Mart When We Start. A small Streamlit shop with categories, cart and orders."""

from __future__ import annotations

import html
import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_NAME = "Mart When We Start"
SHORT = "MWWS"
HERE = Path(__file__).parent
PRODUCTS_CSV = HERE / "products.csv"
ORDERS_CSV = HERE / "orders.csv"

DELIVERY_FEE = 150          # PKR
FREE_DELIVERY_OVER = 3000   # PKR
PRODUCT_COLS = ["id", "name", "category", "price_pkr", "unit", "emoji", "stock", "image_url"]
ORDER_COLS = ["order_id", "time", "name", "phone", "address", "items", "subtotal",
              "delivery", "total", "status"]

st.set_page_config(page_title=f"{SHORT} · {APP_NAME}", page_icon="🛒", layout="wide")


# ---------------------------------------------------------------- helpers
def secret(key: str) -> str:
    try:
        val = st.secrets.get(key, "")
    except Exception:
        val = ""
    return str(val or os.environ.get(key, ""))


def pkr(x: float) -> str:
    return f"Rs {int(round(x)):,}"


def load_products() -> pd.DataFrame:
    if PRODUCTS_CSV.exists():
        df = pd.read_csv(PRODUCTS_CSV)
    else:
        df = pd.DataFrame(columns=PRODUCT_COLS)
    return clean_products(df)


def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    """Fill gaps, fix types and give new rows an ID."""
    df = df.copy()
    for c in PRODUCT_COLS:
        if c not in df:
            df[c] = None
    df = df[PRODUCT_COLS]
    df = df[df["name"].notna() & (df["name"].astype(str).str.strip() != "")].copy()
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    missing = df["id"].isna()
    if missing.any():
        start = int(df["id"].max()) + 1 if df["id"].notna().any() else 1
        df.loc[missing, "id"] = range(start, start + int(missing.sum()))
    df["id"] = df["id"].astype(int)
    df["price_pkr"] = pd.to_numeric(df["price_pkr"], errors="coerce").fillna(0)
    df["stock"] = pd.to_numeric(df["stock"], errors="coerce").fillna(0).astype(int)
    df["category"] = df["category"].fillna("Other").astype(str).str.strip()
    df["unit"] = df["unit"].fillna("piece").astype(str)
    df["emoji"] = df["emoji"].fillna("🛍️").astype(str)
    df["image_url"] = df["image_url"].fillna("").astype(str).str.strip()
    return df.reset_index(drop=True)


def save_products(df: pd.DataFrame) -> None:
    df[PRODUCT_COLS].to_csv(PRODUCTS_CSV, index=False)


def load_orders() -> pd.DataFrame:
    if ORDERS_CSV.exists():
        return pd.read_csv(ORDERS_CSV, dtype={"phone": str})
    return pd.DataFrame(columns=ORDER_COLS)


def save_orders(df: pd.DataFrame) -> None:
    df[ORDER_COLS].to_csv(ORDERS_CSV, index=False)


def cart_lines(products: pd.DataFrame):
    by_id = products.set_index("id")
    lines = []
    for pid, qty in list(st.session_state.cart.items()):
        if pid not in by_id.index:
            st.session_state.cart.pop(pid)
            continue
        p = by_id.loc[pid]
        lines.append({"id": pid, "name": p["name"], "emoji": p["emoji"], "unit": p["unit"],
                      "price": float(p["price_pkr"]), "qty": qty, "stock": int(p["stock"]),
                      "total": float(p["price_pkr"]) * qty})
    return lines


def add_to_cart(pid: int, qty: int, stock: int) -> None:
    current = st.session_state.cart.get(pid, 0)
    st.session_state.cart[pid] = min(current + qty, stock)
    st.toast("Added to cart 🛒")


# ---------------------------------------------------------------- state
st.session_state.setdefault("cart", {})
st.session_state.setdefault("last_order", None)
st.session_state.setdefault("admin_ok", False)
products = load_products()
categories = sorted(products["category"].unique().tolist())
cart_count = sum(st.session_state.cart.values())

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(f"## 🛒 {SHORT}")
    st.caption(APP_NAME)
    page = st.radio("Go to", ["🛍️ Shop", "🛒 Cart", "🔐 Admin"], key="page",
                    label_visibility="collapsed")
    if cart_count:
        st.success(f"🛒 {cart_count} item(s) in cart")
    st.divider()
    st.caption(f"🚚 Delivery {pkr(DELIVERY_FEE)} · free over {pkr(FREE_DELIVERY_OVER)}")
    st.caption("💵 Cash on delivery")


# ---------------------------------------------------------------- shop
def shop_page():
    st.title(f"🛒 {APP_NAME}")
    st.caption("Laundry, clothes and daily essentials — delivered to your door.")

    left, right = st.columns([3, 1])
    with left:
        cat = st.pills("Category", ["All"] + categories, default="All",
                       label_visibility="collapsed") or "All"
    with right:
        q = st.text_input("Search", placeholder="🔍 Search products",
                          label_visibility="collapsed").strip().lower()

    view = products if cat == "All" else products[products["category"] == cat]
    if q:
        view = view[view["name"].str.lower().str.contains(re.escape(q))]
    if view.empty:
        st.info("No products found.")
        return

    cols = st.columns(4)
    for i, p in enumerate(view.itertuples()):
        with cols[i % 4].container(border=True):
            if p.image_url.startswith("http"):
                st.markdown(f"<img src='{html.escape(p.image_url, quote=True)}' "
                            "style='width:100%;height:180px;object-fit:cover;border-radius:8px'>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='font-size:2.6rem;text-align:center'>{p.emoji}</div>",
                            unsafe_allow_html=True)
            st.markdown(f"**{p.name}**")
            st.caption(f"{p.category} · per {p.unit}")
            st.markdown(f"### {pkr(p.price_pkr)}")
            if p.stock <= 0:
                st.button("Out of stock", key=f"oos{p.id}", disabled=True,
                          width="stretch")
                continue
            in_cart = st.session_state.cart.get(p.id, 0)
            room = p.stock - in_cart
            if room <= 0:
                st.caption(f"✅ {in_cart} in cart (max stock)")
                continue
            a, b = st.columns([1, 1])
            qty = a.number_input("Qty", 1, int(room), 1, key=f"q{p.id}",
                                 label_visibility="collapsed")
            b.button("Add", key=f"add{p.id}", type="primary", width="stretch",
                     on_click=add_to_cart, args=(p.id, int(qty), int(p.stock)))
            if in_cart:
                st.caption(f"✅ {in_cart} in cart")


# ---------------------------------------------------------------- cart
def cart_page():
    st.title("🛒 Your cart")

    if st.session_state.last_order:
        o = st.session_state.last_order
        st.success(f"Order **{o['order_id']}** placed! Total {pkr(o['total'])}. "
                   "We'll call you to confirm. Shukriya! 🙏")
        wa = re.sub(r"\D", "", secret("SHOP_WHATSAPP"))
        if wa:
            msg = urllib.parse.quote(f"Assalam o Alaikum, my {SHORT} order {o['order_id']}:\n"
                                     f"{o['items']}\nTotal: {pkr(o['total'])}")
            st.link_button("📲 Send order on WhatsApp", f"https://wa.me/{wa}?text={msg}")
        if st.button("Continue shopping"):
            st.session_state.last_order = None
            st.rerun()
        return

    lines = cart_lines(products)
    if not lines:
        st.info("Your cart is empty. Pick something from the shop 🛍️")
        return

    for ln in lines:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
            c1.markdown(f"{ln['emoji']} **{ln['name']}**  \n{pkr(ln['price'])} / {ln['unit']}")
            new_q = c2.number_input("Qty", 1, max(ln["stock"], 1), min(ln["qty"], max(ln["stock"], 1)),
                                    key=f"cq{ln['id']}", label_visibility="collapsed")
            if new_q != ln["qty"]:
                st.session_state.cart[ln["id"]] = int(new_q)
                st.rerun()
            c3.markdown(f"**{pkr(ln['total'])}**")
            if c4.button("🗑️", key=f"rm{ln['id']}", help="Remove"):
                st.session_state.cart.pop(ln["id"])
                st.rerun()

    subtotal = sum(l["total"] for l in lines)
    delivery = 0 if subtotal >= FREE_DELIVERY_OVER else DELIVERY_FEE
    total = subtotal + delivery
    m1, m2, m3 = st.columns(3)
    m1.metric("Subtotal", pkr(subtotal))
    m2.metric("Delivery", "Free" if delivery == 0 else pkr(delivery))
    m3.metric("Total", pkr(total))
    if delivery:
        st.caption(f"Add {pkr(FREE_DELIVERY_OVER - subtotal)} more for free delivery.")

    st.subheader("Checkout")
    with st.form("checkout"):
        name = st.text_input("Full name")
        phone = st.text_input("Mobile number", placeholder="03XX XXXXXXX")
        address = st.text_area("Delivery address", placeholder="House, street, area, city")
        st.radio("Payment", ["Cash on delivery"], horizontal=True)
        submitted = st.form_submit_button("✅ Place order", type="primary")

    if submitted:
        digits = re.sub(r"\D", "", phone)
        if digits.startswith("92"):
            digits = "0" + digits[2:]
        errors = []
        if len(name.strip()) < 2:
            errors.append("Please enter your name.")
        if not re.fullmatch(r"03\d{9}", digits):
            errors.append("Mobile number should look like 03XX XXXXXXX.")
        if len(address.strip()) < 8:
            errors.append("Please enter a full delivery address.")
        fresh = load_products().set_index("id")
        for ln in lines:
            if ln["id"] not in fresh.index or fresh.loc[ln["id"], "stock"] < ln["qty"]:
                errors.append(f"Sorry, not enough stock for {ln['name']}.")
        if errors:
            for e in errors:
                st.error(e)
            return

        order_id = f"{SHORT}-{datetime.now():%y%m%d-%H%M%S}"
        items = "; ".join(f"{l['name']} x{l['qty']}" for l in lines)
        orders = load_orders()
        row = dict(order_id=order_id, time=f"{datetime.now():%Y-%m-%d %H:%M}",
                   name=name.strip(), phone=digits, address=address.strip(), items=items,
                   subtotal=subtotal, delivery=delivery, total=total, status="New")
        save_orders(pd.concat([orders, pd.DataFrame([row])], ignore_index=True))
        for ln in lines:
            fresh.loc[ln["id"], "stock"] -= ln["qty"]
        save_products(fresh.reset_index())
        st.session_state.cart = {}
        st.session_state.last_order = row
        st.rerun()


# ---------------------------------------------------------------- admin
def admin_page():
    st.title("🔐 Admin")
    pw = secret("ADMIN_PASSWORD")
    if not pw:
        st.warning("Admin is locked until you set a password.")
        st.markdown("On Streamlit Cloud: **Manage app → Settings → Secrets**, then add:")
        st.code('ADMIN_PASSWORD = "choose-a-strong-password"', language="toml")
        return
    if not st.session_state.admin_ok:
        with st.form("login"):
            typed = st.text_input("Password", type="password")
            if st.form_submit_button("Log in"):
                if typed == pw:
                    st.session_state.admin_ok = True
                    st.rerun()
                st.error("Wrong password.")
        return

    if st.button("Log out"):
        st.session_state.admin_ok = False
        st.rerun()

    t_prod, t_orders = st.tabs(["📦 Products & categories", "🧾 Orders"])

    with t_prod:
        st.caption("Edit cells directly. Add a row at the bottom for a new product. "
                   "Type a new name in Category to create a new category.")
        edited = st.data_editor(
            products, num_rows="dynamic", width="stretch", hide_index=True,
            key="prod_editor",
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "name": st.column_config.TextColumn("Name", required=True),
                "category": st.column_config.TextColumn("Category", required=True),
                "price_pkr": st.column_config.NumberColumn("Price (Rs)", min_value=0, step=10),
                "unit": st.column_config.TextColumn("Unit"),
                "emoji": st.column_config.TextColumn("Icon", max_chars=4),
                "image_url": st.column_config.LinkColumn("Photo link (optional)"),
                "stock": st.column_config.NumberColumn("Stock", min_value=0, step=1),
            },
        )
        if st.button("💾 Save products", type="primary"):
            save_products(clean_products(edited))
            st.success("Saved. Refresh the shop to see changes.")
        st.download_button("⬇️ Download products.csv", products.to_csv(index=False),
                           "products.csv", "text/csv")

    with t_orders:
        orders = load_orders()
        if orders.empty:
            st.info("No orders yet.")
            return
        orders = orders.iloc[::-1].reset_index(drop=True)
        k1, k2, k3 = st.columns(3)
        k1.metric("Orders", len(orders))
        k2.metric("New", int((orders["status"] == "New").sum()))
        k3.metric("Revenue", pkr(pd.to_numeric(orders["total"], errors="coerce").sum()))
        edited_o = st.data_editor(
            orders, width="stretch", hide_index=True, key="order_editor",
            disabled=[c for c in ORDER_COLS if c != "status"],
            column_config={"status": st.column_config.SelectboxColumn(
                "Status", options=["New", "Confirmed", "Delivered", "Cancelled"])},
        )
        if st.button("💾 Save order status"):
            save_orders(edited_o.iloc[::-1])
            st.success("Saved.")
        st.download_button("⬇️ Download orders.csv", load_orders().to_csv(index=False),
                           "orders.csv", "text/csv")


# ---------------------------------------------------------------- router
if page.startswith("🛍️"):
    shop_page()
elif page.startswith("🛒"):
    cart_page()
else:
    admin_page()
