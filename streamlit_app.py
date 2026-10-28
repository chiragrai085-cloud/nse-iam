"""
NSE Stock Analyzer — Streamlit frontend (100% free)
====================================================
Talks to your FastAPI backend on Render (nse_analysis_api.py v2).

INSTALL :  pip install streamlit requests pandas plotly
RUN     :  streamlit run streamlit_app.py

SET YOUR API URL (pick one):
  - edit DEFAULT_API_URL below, or
  - type it in the sidebar, or
  - on Streamlit Community Cloud: Settings -> Secrets -> API_URL = "https://your-app.onrender.com"
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

DEFAULT_API_URL = "https://YOUR-APP.onrender.com"

st.set_page_config(page_title="NSE Stock Analyzer", page_icon="📈", layout="wide")


# ── helpers ───────────────────────────────────────────────────────────────

def get_default_url():
    try:
        return st.secrets["API_URL"]
    except Exception:
        return os.environ.get("API_URL", DEFAULT_API_URL)


API_URL = st.sidebar.text_input("API URL", get_default_url()).rstrip("/")


def call_api(path, params=None, method="GET", json=None):
    """Returns parsed JSON, or None after showing a friendly error."""
    try:
        with st.spinner("Fetching data (free server may need ~50s to wake up)..."):
            r = requests.request(method, f"{API_URL}{path}", params=params, json=json, timeout=120)
        if r.status_code != 200:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            st.error(f"API error {r.status_code}: {detail}")
            return None
        return r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Could not reach the API at {API_URL}. {e}")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def cached_get(url, path, params_tuple):
    r = requests.get(f"{url}{path}", params=dict(params_tuple), timeout=120)
    r.raise_for_status()
    return r.json()


def fmt(v, suffix="", dash="—"):
    return dash if v is None else f"{v:,}{suffix}"


def inr(v):
    if v is None:
        return "—"
    return f"₹{v:,.0f}"


def heatmap(corr: dict, title="Correlation"):
    df = pd.DataFrame(corr)
    fig = px.imshow(df, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdYlGn", title=title)
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True)


COMMON = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "WIPRO", "LT",
          "BHARTIARTL", "MARUTI", "SUNPHARMA", "ADANIENT", "HINDUNILVR", "TATAMOTORS"]


def symbol_input(key, default="RELIANCE"):
    return st.text_input("NSE symbol (without .NS)", default, key=key,
                         help="Examples: " + ", ".join(COMMON[:8])).strip().upper()


st.sidebar.title("📈 NSE Analyzer")
page = st.sidebar.radio(
    "Go to",
    ["Dashboard", "Watchlist", "Market", "Compare", "Risk", "Levels", "Signal", "Backtest", "Portfolio"],
)
st.sidebar.caption("Educational purposes only. Not investment advice.")


# ── pages ─────────────────────────────────────────────────────────────────

def page_dashboard():
    st.header("Stock Dashboard")
    c1, c2 = st.columns([3, 1])
    with c1:
        sym = symbol_input("dash_sym")
    with c2:
        months = st.selectbox("Chart months", [3, 6, 12, 24], index=1)
    if not st.button("Analyze", type="primary", key="dash_go"):
        return

    a = call_api(f"/analyze/{sym}")
    if not a:
        return
    t, f = a["technical"], a["fundamentals"]

    if a.get("corporate_action_flag"):
        st.warning(a.get("corporate_action_note"))

    st.subheader(a["symbol"])
    cols = st.columns(5)
    cols[0].metric("Price", f"₹{fmt(t['current_price'])}")
    cols[1].metric("RSI (14)", fmt(t["rsi_14"]))
    cols[2].metric("MA trend", (t["ma_trend"] or "—").title())
    cols[3].metric("ADX (14)", fmt(t["adx_14"]))
    cols[4].metric("% of 52w high", fmt(t["pct_of_52w_high"], "%"))

    tab1, tab2 = st.tabs(["Technical", "Fundamentals"])
    with tab1:
        st.dataframe(pd.DataFrame(t.items(), columns=["Indicator", "Value"]), hide_index=True, use_container_width=True)
    with tab2:
        fund = {k: v for k, v in f.items() if not k.startswith("_")}
        st.dataframe(pd.DataFrame(fund.items(), columns=["Metric", "Value"]), hide_index=True, use_container_width=True)

    ch = call_api(f"/chart/{sym}", {"months": months})
    if not ch:
        return
    df = pd.DataFrame(ch["data"])
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03,
                        subplot_titles=("Price", "RSI", "MACD"))
    fig.add_trace(go.Candlestick(x=df["date"], open=df["open"], high=df["high"], low=df["low"],
                                 close=df["close"], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["ma_50"], name="MA50", line=dict(width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["ma_200"], name="MA200", line=dict(width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["rsi"], name="RSI"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", row=2, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["macd_line"], name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["macd_signal"], name="Signal"), row=3, col=1)
    fig.update_layout(height=760, xaxis_rangeslider_visible=False, margin=dict(t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def page_watchlist():
    st.header("Watchlist")
    syms = st.text_input("Symbols (comma separated, max 10)", "RELIANCE,TCS,INFY,HDFCBANK")
    if st.button("Load", type="primary"):
        d = call_api("/watchlist", {"symbols": syms})
        if d:
            df = pd.DataFrame(d["stocks"])
            st.dataframe(df, hide_index=True, use_container_width=True)


def page_market():
    st.header("Market Overview")
    d = call_api("/market")
    if not d:
        return
    mood = d.get("market_mood")
    if mood:
        st.info(f"Market mood (India VIX): **{mood.upper()}**")
    cols = st.columns(len(d["indices"]))
    for col, idx in zip(cols, d["indices"]):
        with col:
            if "error" in idx:
                st.warning(f"{idx['name']}: {idx['error']}")
                continue
            st.metric(idx["name"], f"{idx['level']:,}", f"{idx['change']:+,} ({idx['change_pct']:+}%)")
            spark = go.Figure(go.Scatter(y=idx["sparkline"], mode="lines"))
            spark.update_layout(height=90, margin=dict(l=0, r=0, t=0, b=0), xaxis_visible=False, yaxis_visible=False)
            st.plotly_chart(spark, use_container_width=True, key=f"sp_{idx['symbol']}")
            st.caption(f"1-month: {idx['month_change_pct']:+}%")


def page_compare():
    st.header("Compare Stocks")
    c1, c2 = st.columns([3, 1])
    syms = c1.text_input("2–5 symbols, comma separated", "TCS,INFY,WIPRO")
    period = c2.selectbox("Period", ["3mo", "6mo", "1y", "2y", "5y"], index=2)
    if not st.button("Compare", type="primary"):
        return
    d = call_api("/compare", {"symbols": syms, "period": period})
    if not d:
        return
    st.success(f"🏆 Best performer: {d['best_performer']}")
    st.dataframe(pd.DataFrame(d["summary"]), hide_index=True, use_container_width=True)
    ser = pd.DataFrame(d["normalised_series"]).set_index("date")
    fig = px.line(ser, title="Performance rebased to 100")
    st.plotly_chart(fig, use_container_width=True)
    heatmap(d["correlation"], "Return correlation")
    for e in d.get("errors", []):
        st.warning(f"{e['symbol']}: {e['error']}")


def page_risk():
    st.header("Risk Metrics")
    c1, c2 = st.columns([3, 1])
    sym = symbol_input("risk_sym", "TCS")
    period = c2.selectbox("Period", ["1y", "2y", "5y"], index=1)
    if not st.button("Calculate", type="primary"):
        return
    d = call_api(f"/risk/{sym}", {"period": period})
    if not d:
        return
    color = {"low": "green", "moderate": "orange", "high": "red"}[d["risk_level"]]
    st.markdown(f"### Risk level: :{color}[{d['risk_level'].upper()}]")
    rows = [
        ("Annualised return", fmt(d["annualised_return_pct"], "%")),
        ("Annualised volatility", fmt(d["annualised_volatility_pct"], "%")),
        ("Sharpe ratio", fmt(d["sharpe_ratio"])),
        ("Sortino ratio", fmt(d["sortino_ratio"])),
        ("Max drawdown", fmt(d["max_drawdown_pct"], "%")),
        ("Daily VaR 95%", fmt(d["var_95_daily_pct"], "%")),
        ("Daily CVaR 95%", fmt(d["cvar_95_daily_pct"], "%")),
        ("Beta vs Nifty", fmt(d["beta_vs_nifty"])),
        ("Correlation vs Nifty", fmt(d["correlation_vs_nifty"])),
        ("Best day", fmt(d["best_day_pct"], "%")),
        ("Worst day", fmt(d["worst_day_pct"], "%")),
    ]
    for i in range(0, len(rows), 4):
        cols = st.columns(4)
        for col, (k, v) in zip(cols, rows[i:i + 4]):
            col.metric(k, v)
    st.caption("Beta > 1: moves more than the Nifty. VaR 95%: on 1 day in 20 the loss is expected to be at least this bad.")
    dd = pd.DataFrame(d["drawdown_series"])
    fig = px.area(dd, x="date", y="drawdown_pct", title="Drawdown from peak (%)")
    fig.update_traces(line_color="crimson")
    st.plotly_chart(fig, use_container_width=True)


def page_levels():
    st.header("Support / Resistance & Levels")
    sym = symbol_input("lvl_sym")
    if not st.button("Get levels", type="primary"):
        return
    d = call_api(f"/levels/{sym}")
    if not d:
        return
    price = d["current_price"]
    p = d["pivot_points"]
    st.metric("Current price", f"₹{price:,}")

    ladder = [("R3", p["r3"]), ("R2", p["r2"]), ("R1", p["r1"]), ("Pivot", p["pivot"]),
              ("S1", p["s1"]), ("S2", p["s2"]), ("S3", p["s3"])]
    fig = go.Figure()
    for name, v in ladder:
        fig.add_hline(y=v, line_dash="dot", annotation_text=f"{name} {v}",
                      line_color="red" if name.startswith("R") else "green" if name.startswith("S") else "gray")
    fig.add_hline(y=price, line_color="blue", line_width=3, annotation_text=f"Price {price}")
    ys = [v for _, v in ladder] + [price]
    fig.update_yaxes(range=[min(ys) * 0.99, max(ys) * 1.01])
    fig.update_layout(height=450, title="Pivot ladder", xaxis_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.write("**Nearest resistance**")
    c1.write(d["nearest_resistance"] or "—")
    c2.write("**Nearest support**")
    c2.write(d["nearest_support"] or "—")
    c3.metric("52w range", f"{d['low_52w']:,} – {d['high_52w']:,}")

    c1, c2, c3 = st.columns(3)
    c1.metric("ATR (14)", fmt(d["atr_14"]), f"{d['atr_pct_of_price']}% of price", delta_color="off")
    c2.metric("Stop-loss (2×ATR)", fmt(d["suggested_stop_loss_2x_atr"]))
    c3.metric("Stochastic %K", fmt(d["stochastic_k"]), d["stochastic_state"], delta_color="off")


def page_signal():
    st.header("Signal Score")
    sym = symbol_input("sig_sym")
    if not st.button("Score it", type="primary"):
        return
    d = call_api(f"/signal/{sym}")
    if not d:
        return
    colors = {"Strong Buy": "green", "Buy": "green", "Hold": "gray", "Sell": "orange", "Strong Sell": "red"}
    st.markdown(f"## :{colors[d['rating']]}[{d['rating']}]  (score {d['score']:+d})")
    st.progress((d["score"] + 7) / 14)
    st.caption(f"Trend strength: {d.get('trend_strength') or '—'}")
    for r in d["reasons"]:
        icon = "🟢" if r["points"] > 0 else "🔴" if r["points"] < 0 else "⚪"
        st.write(f"{icon} **{r['points']:+d}** — {r['reason']}")
    st.caption(d["disclaimer"])


def page_backtest():
    st.header("Backtest: MA Crossover vs Buy & Hold")
    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
    with c1:
        sym = symbol_input("bt_sym", "INFY")
    fast = c2.number_input("Fast MA", 5, 100, 50)
    slow = c3.number_input("Slow MA", 20, 300, 200)
    period = c4.selectbox("Period", ["2y", "5y", "10y", "max"], index=1)
    cost = c5.number_input("Cost/trade %", 0.0, 2.0, 0.1, 0.05)
    if not st.button("Run backtest", type="primary"):
        return
    if fast >= slow:
        st.error("Fast MA must be smaller than slow MA.")
        return
    d = call_api(f"/backtest/{sym}", {"fast": int(fast), "slow": int(slow), "period": period, "cost_pct": cost})
    if not d:
        return
    st.info(d["verdict"])
    ec = pd.DataFrame(d["equity_curve"]).set_index("date")
    st.plotly_chart(px.line(ec, title="Growth of 100"), use_container_width=True)
    comp = pd.DataFrame({
        "Strategy": d["strategy"],
        "Buy & Hold": {**d["buy_and_hold"], "sharpe_ratio": None, "number_of_trades": 1, "time_in_market_pct": 100},
    })
    st.dataframe(comp, use_container_width=True)
    st.caption(d["disclaimer"])


def page_portfolio():
    st.header("Portfolio Analyzer")
    if "holdings" not in st.session_state:
        st.session_state["holdings"] = pd.DataFrame([
            {"symbol": "RELIANCE", "quantity": 10, "buy_price": 2400.0},
            {"symbol": "TCS", "quantity": 5, "buy_price": 3500.0},
            {"symbol": "INFY", "quantity": 15, "buy_price": 1500.0},
        ])
    edited = st.data_editor(st.session_state["holdings"], num_rows="dynamic", use_container_width=True,
                            key="holdings_editor")
    if not st.button("Analyze portfolio", type="primary"):
        return
    clean = edited.dropna()
    clean = clean[clean["symbol"].astype(str).str.strip() != ""]
    holdings = [
        {"symbol": str(r.symbol).strip().upper(), "quantity": float(r.quantity), "buy_price": float(r.buy_price)}
        for r in clean.itertuples()
    ]
    if not holdings:
        st.error("Add at least one holding.")
        return
    d = call_api("/portfolio", method="POST", json={"holdings": holdings})
    if not d:
        return

    s = d["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invested", inr(s["total_invested"]))
    c2.metric("Current value", inr(s["current_value"]))
    c3.metric("P&L", inr(s["total_pnl"]), f"{s['total_pnl_pct']}%")
    c4.metric("Largest position", s["largest_position"])
    if s["concentration_warning"]:
        st.warning("⚠️ One stock is more than 40% of your portfolio — consider diversifying.")

    h = pd.DataFrame(d["holdings"])
    left, right = st.columns([3, 2])
    left.dataframe(h, hide_index=True, use_container_width=True)
    right.plotly_chart(px.pie(h, names="symbol", values="weight_pct", hole=0.5, title="Allocation"),
                       use_container_width=True)

    if d["risk"]:
        st.subheader("Portfolio risk")
        r = d["risk"]
        cols = st.columns(4)
        cols[0].metric("Volatility", fmt(r.get("annual_volatility_pct"), "%"))
        cols[1].metric("Max drawdown", fmt(r.get("max_drawdown_pct"), "%"))
        cols[2].metric("Sharpe", fmt(r.get("sharpe_ratio")))
        cols[3].metric("Daily VaR 95%", fmt(r.get("var_95_daily_pct"), "%"))
        if r.get("diversification"):
            st.write(f"Diversification: **{r['diversification'].upper()}** "
                     f"(avg correlation {r.get('avg_pairwise_correlation')})")
    if d.get("correlation"):
        heatmap(d["correlation"], "Holdings correlation")
    for e in d.get("errors", []):
        st.warning(f"{e['symbol']}: {e['error']}")


PAGES = {
    "Dashboard": page_dashboard, "Watchlist": page_watchlist, "Market": page_market,
    "Compare": page_compare, "Risk": page_risk, "Levels": page_levels,
    "Signal": page_signal, "Backtest": page_backtest, "Portfolio": page_portfolio,
}
PAGES[page]()
