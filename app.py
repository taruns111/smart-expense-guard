import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from backend import (
    send_otp_email,
    verify_otp_and_login,
    add_personal_expense,
    get_user_expenses,
    get_total_spend,
    delete_current_month_expenses,
    delete_expense,
    update_expense
)

st.set_page_config(page_title="Smart Expense Guard", layout="wide")

# ------------------- UI THEME --------------------
st.markdown("""
<style>
.stApp { background-color: #0e1117; }
h1,h2,h3 { color:#4CAF50; }
.card {
    background:#262730;
    padding:20px;
    border-radius:15px;
    text-align:center;
    margin-bottom:10px;
}
</style>
""", unsafe_allow_html=True)

# ================= CACHED DATA FETCH =================
# FIX: @st.cache_data — DB hit sirf tab hoga jab user_id badlega ya ttl expire hoga.
# Pehle har Streamlit rerun pe DB call hoti thi — ab nahi hogi.

@st.cache_data(ttl=30)   # 30 sec cache — add/edit/delete ke baad auto-invalidate hoga
def load_expenses(user_id):
    return get_user_expenses(user_id)

def invalidate_cache(user_id):
    """Delete ke baad / add ke baad cache clear karo taaki fresh data aaye."""
    load_expenses.clear()

# ================= LOGIN =================
if "user_id" not in st.session_state:
    st.title("🔐 Smart Expense Guard - Login")

    col1, col2 = st.columns(2)

    with col1:
        email = st.text_input("📧 Enter Email")
        if st.button("Send OTP"):
            if not email:
                st.error("Please enter email")
            else:
                res = send_otp_email(email)
                if res["status"] == "success":
                    st.success("OTP sent to your email 📧")
                else:
                    st.error(res["msg"])

    with col2:
        otp = st.text_input("🔑 Enter OTP")
        if st.button("Verify OTP"):
            if not email or not otp:
                st.error("Enter email and OTP")
            else:
                result = verify_otp_and_login(email, otp)
                if result["status"] == "success":
                    st.session_state["user_id"] = result["user_id"]
                    st.rerun()
                else:
                    st.error(result["msg"])

# ================= MAIN APP =================
else:
    user_id = st.session_state["user_id"]

    st.sidebar.title("📊 Smart Expense Guard")
    menu = st.sidebar.radio("Menu", ["Dashboard", "Add Expense", "Analytics", "Settings"])

    # FIX: Cached call — sirf ek DB hit per 30 sec
    expenses = load_expenses(user_id)
    df = pd.DataFrame(expenses) if expenses else pd.DataFrame()

    if not df.empty:
        df["amount"]       = pd.to_numeric(df["amount"])
        df["expense_date"] = pd.to_datetime(df["expense_date"])

    # ========================= DASHBOARD =========================
    if menu == "Dashboard":
        st.title("💰 Dashboard")

        if not df.empty:
            # FIX: today ek baar compute karo, baar baar nahi
            today       = pd.Timestamp.today().normalize()
            month_start = today.replace(day=1)

            today_spend = df[df["expense_date"] == today]["amount"].sum()
            month_spend = df[df["expense_date"] >= month_start]["amount"].sum()
            avg_spend   = df["amount"].mean()

            # FIX: total_spend ab df se compute — alag DB call nahi
            total = df["amount"].sum()

            col1, col2, col3, col4 = st.columns(4)
            col1.markdown(f"<div class='card'><h3>Total</h3><h1>₹ {round(total,2)}</h1></div>",       unsafe_allow_html=True)
            col2.markdown(f"<div class='card'><h3>Today</h3><h1>₹ {round(today_spend,2)}</h1></div>", unsafe_allow_html=True)
            col3.markdown(f"<div class='card'><h3>This Month</h3><h1>₹ {round(month_spend,2)}</h1></div>", unsafe_allow_html=True)
            col4.markdown(f"<div class='card'><h3>Avg Expense</h3><h1>₹ {round(avg_spend,2)}</h1></div>", unsafe_allow_html=True)

        st.subheader("🧾 Expense Manager")

        if not df.empty:
            # ---------- Filters ----------
            col1, col2, col3 = st.columns(3)

            with col1:
                category_filter = st.selectbox("Filter Category", ["All"] + sorted(df["category"].unique().tolist()))
            with col2:
                start_date = st.date_input("Start Date", df["expense_date"].min())
            with col3:
                end_date = st.date_input("End Date", df["expense_date"].max())

            search = st.text_input("🔍 Search (description/category)")

            filtered_df = df.copy()

            if category_filter != "All":
                filtered_df = filtered_df[filtered_df["category"] == category_filter]

            filtered_df = filtered_df[
                (filtered_df["expense_date"] >= pd.to_datetime(start_date)) &
                (filtered_df["expense_date"] <= pd.to_datetime(end_date))
            ]

            if search:
                mask = (
                    filtered_df["description"].str.contains(search, case=False, na=False) |
                    filtered_df["category"].str.contains(search, case=False, na=False)
                )
                filtered_df = filtered_df[mask]

            filtered_df = filtered_df.sort_values(by="expense_date", ascending=False)

            # ---------- Export ----------
            st.download_button(
                "📥 Download Excel",
                filtered_df.to_csv(index=False),
                file_name="expenses.csv",
                mime="text/csv"
            )

            st.dataframe(filtered_df, use_container_width=True)

            # ---------- Edit / Delete ----------
            st.subheader("✏️ Edit / ❌ Delete Expense")

            # FIX: iterrows() se bach ke itertuples() use karo — 3-4x faster for large df
            for row in filtered_df.itertuples(index=False):
                c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 3, 1, 1])
                c1.write(row.category)
                c2.write(row.amount)
                c3.write(row.expense_date.date())
                c4.write(row.description)

                if c5.button("❌", key=f"del_{row.expense_id}"):
                    delete_expense(row.expense_id)
                    invalidate_cache(user_id)
                    st.rerun()

                if c6.button("✏️", key=f"edit_{row.expense_id}"):
                    st.session_state["edit_id"] = row.expense_id

            # ---------- Edit Form ----------
            if "edit_id" in st.session_state:
                edit_rows = df[df["expense_id"] == st.session_state["edit_id"]]
                if not edit_rows.empty:
                    edit_row = edit_rows.iloc[0]
                    st.subheader("✏️ Update Expense")

                    new_amount   = st.number_input("Amount", value=float(edit_row["amount"]))
                    cat_options  = ["Food", "Travel", "Rent", "Medical", "Shopping", "Entertainment", "Others"]
                    new_category = st.selectbox(
                        "Category", cat_options,
                        index=cat_options.index(edit_row["category"]) if edit_row["category"] in cat_options else 0
                    )
                    new_desc = st.text_input("Description", value=edit_row["description"])

                    if st.button("Update Expense"):
                        update_expense(edit_row["expense_id"], new_amount, new_category, new_desc)
                        del st.session_state["edit_id"]
                        invalidate_cache(user_id)
                        st.success("Updated ✅")
                        st.rerun()
        else:
            st.info("No expenses found")

    # ========================= ADD EXPENSE =========================
    elif menu == "Add Expense":
        st.title("➕ Add Expense")

        with st.form("expense_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                category = st.selectbox(
                    "Category",
                    ["Food", "Travel", "Rent", "Medical", "Shopping", "Entertainment", "Others"]
                )
            with col2:
                amount = st.number_input("Amount", min_value=0.0, step=1.0)

            description = st.text_input("Description")
            submit      = st.form_submit_button("Add Expense")

            if submit:
                add_personal_expense(user_id, amount, category, description)
                invalidate_cache(user_id)
                st.success("Expense added ✅")
                st.rerun()

    # ========================= ANALYTICS =========================
    elif menu == "Analytics":
        st.title("📊 Analytics")

        if not df.empty:
            # FIX: groupby agg ek baar — do alag calls ki jagah
            cat_summary = df.groupby("category", as_index=False)["amount"].sum()

            col1, col2 = st.columns(2)
            with col1:
                fig = px.pie(cat_summary, names="category", values="amount", title="Category-wise Expense")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig = px.bar(cat_summary, x="category", y="amount", title="Category-wise Bar Chart")
                st.plotly_chart(fig, use_container_width=True)

            # FIX: dt.to_period slow hai large df pe — strftime use karo
            df["month"]   = df["expense_date"].dt.strftime("%Y-%m")
            month_summary = df.groupby("month", as_index=False)["amount"].sum().sort_values("month")

            fig = px.line(month_summary, x="month", y="amount", markers=True, title="Monthly Trend")
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("No data available")

    # ========================= SETTINGS =========================
    elif menu == "Settings":
        st.title("⚙️ Settings")

        st.subheader("💸 Monthly Budget")

        if "budget" not in st.session_state:
            st.session_state.budget = 5000

        budget = st.number_input("Set Monthly Budget", value=float(st.session_state.budget))

        if st.button("Save Budget"):
            st.session_state.budget = budget
            st.success("Budget Updated ✅")

        # FIX: total ab df se — alag get_total_spend() DB call nahi
        total = df["amount"].sum() if not df.empty else 0.0
        if total > st.session_state.budget:
            st.error(f"⚠️ Budget exceeded! Limit ₹{st.session_state.budget}")

        st.subheader("🗑️ Delete This Month Data")
        confirm = st.checkbox("I confirm to delete this month's data")

        if confirm and st.button("Delete Data"):
            res = delete_current_month_expenses(user_id)
            invalidate_cache(user_id)
            st.success(res["msg"])
            st.rerun()

        if st.button("Logout"):
            invalidate_cache(user_id)
            del st.session_state["user_id"]
            st.rerun()
