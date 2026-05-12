import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import date

# --- 1. SETTINGS & DATA ---
PERIODS = {
    "Meeting 1 to 2": {"start": "2025-01-06", "end": "2025-09-06"},
    "Meeting 2 to 3": {"start": "2025-09-08", "end": None}
}
# Pulling data from st.secrets
PURCHASE_PRICES = st.secrets["PURCHASE_PRICES"]
PORTFOLIO_MAP = st.secrets["PORTFOLIO_MAP"]
CASH_CONTRIBUTIONS = st.secrets["CASH_CONTRIBUTIONS"]

# --- 2. FX HELPER FUNCTIONS ---
def get_gbp_conversion(ticker, local_val, fx_row, is_entry=True):
    """
    Converts foreign currency to GBP and applies the 0.15% T212 fee.
    """
    if ticker.endswith(".MI"):
        rate = fx_row["GBPEUR=X"]
    elif ".L" in ticker:
        # Assuming London tickers are in GBp (pence), divide by 100 for GBP
        # If your specific ticker is already in GBP, remove the / 100
        return local_val / 100 
    else:
        rate = fx_row["GBPUSD=X"]
    
    gbp_val = local_val / rate
    fee = 0.0015
    # On entry, you pay more; on exit, you receive less.
    return gbp_val * (1 + fee) if is_entry else gbp_val * (1 - fee)


# --- 2. CALCULATION ENGINE ---
@st.cache_data(ttl=3600)
def calculate_period_leaderboard(period_key, start, end,_portfolios):
    # Get all tickers plus FX pairs
    stock_tickers = list(set(tk for p in portfolios.values() for tk in p))
    fx_tickers = ["GBPUSD=X", "GBPEUR=X"]

    data = yf.download(stock_tickers + fx_tickers, start=start, end=end, auto_adjust=True)["Open"]
    data = data.dropna(how='any')
    
    if data.empty:
        st.error("No overlapping trading days found.")
        return pd.DataFrame()

    # First row FX rates for the 'Purchase' and last row for 'Current'
    first_row = data.iloc[0]
    last_row = data.iloc[-1]

    # Get hardcoded prices for this period
    period_purchase_prices = PURCHASE_PRICES[period_key]

    results = []
    for friend, holdings in portfolios.items():
        total_invested_gbp = 0
        current_value_gbp = 0
        
        for tk, qty in holdings.items():
            # PURCHASE COST (Hardcoded Price * First Row FX)
            buy_price_local = period_purchase_prices[tk]
            buy_val_local = buy_price_local * qty
            total_invested_gbp += get_gbp_conversion(tk, buy_val_local, first_row, is_entry=True)
    
            # CURRENT VALUE (Yahoo Price * Last Row FX)
            current_price_local = last_row[tk]
            current_val_local = current_price_local * qty
            current_value_gbp += get_gbp_conversion(tk, current_val_local, last_row, is_entry=False)

        profit = current_value_gbp - total_invested_gbp
        roi = (profit / total_invested_gbp) * 100 if total_invested_gbp != 0 else 0

        results.append({
            "Name": friend,
            "Invested": total_invested_gbp, # Derived from shares, not hardcoded cash
            "Balance": current_value_gbp,
            "Gain/Loss": profit,
            "% Change": roi
        })
    
    df = pd.DataFrame(results).sort_values("% Change", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "Rank"
    return df

# Perform calculations before rendering tabs
p1_data = calculate_period_leaderboard("Meeting_1", PERIODS["Meeting 1 to 2"]["start"], PERIODS["Meeting 1 to 2"]["end"], PORTFOLIO_MAP["Meeting_1_to_2"])

p2_data = calculate_period_leaderboard("Meeting_2", PERIODS["Meeting 2 to 3"]["start"], PERIODS["Meeting 2 to 3"]["end"], PORTFOLIO_MAP["Meeting_2_to_3"])


# --- 3. TOTAL JOURNEY LOGIC ---
total_stats = []
for member, invested in CASH_CONTRIBUTIONS.items():
    p1_match = p1_data[p1_data['Name'] == member]
    p1_profit = p1_match['Gain/Loss'].values[0] if not p1_match.empty else 0
    p1_invested = p1_match['Invested'].values[0] if not p1_match.empty else 0

    p2_match = p2_data[p2_data['Name'] == member]
    
    if not p2_match.empty:
        p2_profit = p2_match['Gain/Loss'].values[0]
        p2_invested = p2_match['Invested'].values[0]
        current_val = p2_match['Balance'].values[0]
        status = "Active"
    else:
        p2_profit = 0
        p2_invested = 0
        p1_match = p1_data[p1_data['Name'] == member]
        if not p1_match.empty:
            current_val = p1_match['Balance'].values[0]
            status = "Exited"
        else:
            current_val, status = 0, "Unknown"

    total_profit = p1_profit + p2_profit
    total_invested = p1_invested + p2_invested

    roi = (total_profit / invested) * 100 if invested != 0 else 0
    total_stats.append({
        "Name": member,
        "Status": status,
        #"Invested": total_invested, # Use actual invested amount from calculations
        "Current": current_val,
        "Total P/L": total_profit,
        "% Return": roi
    })

total_df = pd.DataFrame(total_stats).sort_values("% Return", ascending=False).reset_index(drop=True)
total_df.index = total_df.index + 1
total_df.index.name = "Rank"

# --- 4. DISPLAY ---
st.title("📈 Investment Club Leaderboard")
tab_total, tab_p1, tab_p2 = st.tabs(["Total Journey", "Period 1 (Jan-Sep)", "Period 2 (Sep-Now)"])

with tab_total:
    st.header("Overall Performance (Since Day 1)")
    st.dataframe(total_df.style.format({
        "Invested": "{:,.2f}", "Current": "{:,.2f}",
        "Total P/L": "{:+,.2f}", "% Return": "{:+.2f}%"
    }),use_container_width=True)

with tab_p1:
    st.header("Meeting 1 ➔ Meeting 2")
    st.dataframe(p1_data.style.format({"Balance": "{:,.2f}", "Gain/Loss": "{:+,.2f}", "% Change": "{:+.2f}%"}), use_container_width=True)

with tab_p2:
    st.header("Meeting 2 ➔ Today")
    st.dataframe(p2_data.style.format({"Balance": "{:,.2f}", "Gain/Loss": "{:+,.2f}", "% Change": "{:+.2f}%"}), use_container_width=True)
