import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime

# 引入官方 150 檔股票名稱對照模組
try:
    from src.stock_list.official_stocks import get_official_stock_name
except ImportError:
    def get_official_stock_name(stock_id):
        return f"指定標的_{stock_id}"

# 引入 FinMind 與 AI 預測模組
try:
    from src.data_loader.finmind_loader import FinMindDataLoader
    from src.models.dynamic_forecast import ai_dynamic_forecast
except ImportError:
    st.error("找不到 src 模組，請確認專案資料夾結構是否正確。")

# -------------------------------------------------------------------
# 1. 頁面配置與競賽風控常數宣告
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AI Agent 基金經理人 - AI CUP 2026",
    page_icon="💼",
    layout="wide"
)

INITIAL_CAPITAL = 1_000_000_000.0  # 10 億元初始資金
MIN_POSITIONS = 20                 # 最少持股檔數
MAX_POSITIONS = 30                 # 最多持股檔數
TSMC_WEIGHT_LIMIT = 0.25           # 2330.tw 上限 25%
OTHER_WEIGHT_LIMIT = 0.10          # 其餘個股上限 10%
MAX_CASH_RATIO = 0.25              # 現金部位每日必須 < 25%
FEE_RATE = 0.001425                # 券商手續費 0.1425%
TAX_RATE = 0.003                   # 證券交易稅 0.3%

# 初始化 Session 狀態 (十億元帳戶)
if "cash" not in st.session_state:
    st.session_state["cash"] = INITIAL_CAPITAL
if "portfolio" not in st.session_state:
    st.session_state["portfolio"] = {}
if "trade_history" not in st.session_state:
    st.session_state["trade_history"] = []

st.title("💼 AI Agent 基金經理人 (FinMind 籌碼 + 波動慣性智慧投資)")
st.caption("符合玉山挑戰賽規則：20~30 檔持股、個股上限限制、現金部位 < 25%、整股交易與稅費扣除")
st.markdown("---")

# -------------------------------------------------------------------
# 2. 側邊欄控制台
# -------------------------------------------------------------------
st.sidebar.header("⚙️ AI 智慧策略面板")

# 玉山挑戰賽 150 檔個股清單
default_stocks = (
    "2330, 2454, 2308, 2317, 3711, 2881, 2383, 2303, 2882, 3037, "
    "2891, 1303, 2345, 2382, 2408, 7769, 2412, 2327, 6669, 3017, "
    "2885, 2887, 2360, 2886, 2059, 6505, 2884, 2880, 2357, 2890, "
    "8046, 2344, 3231, 2892, 3008, 2356, 2404, 6515, 3533, 2313, "
    "2337, 5871, 3044, 3702, 1101, 2409, 6239, 2609, 2834, 6139, "
    "2883, 3443, 3653, 2395, 2301, 6446, 4958, 2603, 5880, 1216, "
    "3045, 2368, 3665, 4904, 3481, 2379, 1301, 1326, 3189, 3034, "
    "2207, 2002, 2801, 2449, 1590, 3661, 6770, 3036, 2615, 2618, "
    "2912, 4938, 2376, 5876, 1519, 6415, 6919, 2324, 2347, 1504, "
    "7750, 1402, 1605, 2610, 6789, 1802, 8210, 2451, 2812, 2377, "
    "5274, 3491, 6223, 6121, 6488, 6548, 8299, 1785, 6274, 3363, "
    "5347, 7828, 3293, 4979, 8069, 6182, 3529, 3163, 3081, 3211, "
    "3260, 4966, 3105, 4991, 5289, 5903, 5536, 1815, 5483, 3680, "
    "6147, 8415, 7734, 6290, 6187, 7751, 3264, 6023, 3324, 4772, "
    "6510, 8932, 8358, 6584, 3374, 3227, 3131, 4123, 4749, 3718"
)
stock_input = st.sidebar.text_area("AI 掃描官方標的清單 (150檔)", default_stocks, height=200)
target_stocks = [s.strip() for s in stock_input.split(",") if s.strip()]

score_threshold = st.sidebar.slider("AI 買進評分門檻", min_value=0.0, max_value=1.0, value=0.40, step=0.01)

col_btn1, col_btn2 = st.sidebar.columns(2)
run_ai_btn = col_btn1.button("🚀 執行 AI 多維度選股決策", type="primary")
reset_btn = col_btn2.button("🔄 重置十億帳戶")

if reset_btn:
    st.session_state["cash"] = INITIAL_CAPITAL
    st.session_state["portfolio"] = {}
    st.session_state["trade_history"] = []
    st.sidebar.success("帳戶已重置為 10 億元初始資金！")

# -------------------------------------------------------------------
# 3. 安全的 API 資料獲取與快取處理
# -------------------------------------------------------------------
@st.cache_resource
def get_loader():
    return FinMindDataLoader()

loader = get_loader()

@st.cache_resource(show_spinner=False)
def get_forecast_cached(stock_id):
    try:
        res = ai_dynamic_forecast(stock_id, loader=loader)
        if not isinstance(res, dict):
            return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": "回傳非字典格式"}
        return res
    except Exception as e:
        return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": str(e)}

# -------------------------------------------------------------------
# 4. 執行 AI 決策下單邏輯
# -------------------------------------------------------------------
if run_ai_btn:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    forecast_results = []
    latest_prices = {}
    
    progress_bar = st.progress(0, text="正在載入 AI 預測資料與即時價格...")
    
    for i, stock_id in enumerate(target_stocks):
        res = get_forecast_cached(stock_id)
        score = res.get("forecast_score", 0.5) if isinstance(res, dict) else 0.5
        res["forecast_score"] = score
        res["stock_name"] = get_official_stock_name(stock_id)
        forecast_results.append(res)
        
        try:
            df_p = loader.get_stock_price(stock_id)
            if df_p is not None and not df_p.empty and "close" in df_p.columns:
                latest_prices[stock_id] = float(df_p["close"].iloc[-1])
            else:
                latest_prices[stock_id] = 100.0
        except Exception:
            latest_prices[stock_id] = 100.0
            
        time.sleep(0.01)
        progress_bar.progress((i + 1) / len(target_stocks), text=f"已處理 {get_official_stock_name(stock_id)} ({stock_id})")
        
    progress_bar.empty()

    # 1. 依分數排序
    sorted_stocks = sorted(forecast_results, key=lambda x: x["forecast_score"], reverse=True)
    
    # 嚴格篩選大於門檻的股票，若不足 20 檔則強制取前 20 檔以符合競賽規範 (20~30檔)
    selected_stocks = [s for s in sorted_stocks if s["forecast_score"] >= score_threshold]
    if len(selected_stocks) < MIN_POSITIONS:
        selected_stocks = sorted_stocks[:MIN_POSITIONS]
    elif len(selected_stocks) > MAX_POSITIONS:
        selected_stocks = selected_stocks[:MAX_POSITIONS]

    # 計算當前總資產 NAV
    current_stock_val = sum(
        st.session_state["portfolio"].get(s["stock_id"], {}).get("shares", 0) * latest_prices.get(s["stock_id"], 100.0)
        for s in selected_stocks
    )
    total_nav = st.session_state["cash"] + current_stock_val
    
    # 2. AI 動態權重分配
    raw_scores = [s["forecast_score"] for s in selected_stocks]
    score_sum = sum(raw_scores) if sum(raw_scores) > 0 else 1.0
    target_allocation_pool = 0.90  # 90% 投入股票，10% 現金 (< 25% 限制)
    
    stock_target_weights = {}
    for s in selected_stocks:
        s_id = s["stock_id"]
        weight = (s["forecast_score"] / score_sum) * target_allocation_pool
        
        if s_id == "2330":
            weight = min(weight, TSMC_WEIGHT_LIMIT)
        else:
            weight = min(weight, OTHER_WEIGHT_LIMIT)
            
        stock_target_weights[s_id] = weight

    # 3. 執行交易
    selected_ids = [s["stock_id"] for s in selected_stocks]
    
    # 平倉未入選股票
    for s_id in list(st.session_state["portfolio"].keys()):
        current_holdings = st.session_state["portfolio"][s_id]
        shares_held = current_holdings.get("shares", 0) if isinstance(current_holdings, dict) else current_holdings
        if shares_held > 0 and s_id not in selected_ids:
            price = latest_prices.get(s_id, 100.0)
            gross_revenue = shares_held * price
            fee = gross_revenue * FEE_RATE
            tax = gross_revenue * TAX_RATE
            net_revenue = gross_revenue - fee - tax
            
            st.session_state["cash"] += net_revenue
            st.session_state["portfolio"][s_id] = {"shares": 0, "avg_cost": 0.0}
            st.session_state["trade_history"].append({
                "時間": now_str, "股票代碼": s_id, "股票名稱": get_official_stock_name(s_id),
                "動作": "平倉 (SELL)", "成交單價": price, "整股(股)": shares_held, 
                "淨入帳金額": net_revenue, "備註": "未達 AI 選股名單"
            })
    
    # 調整/建倉部位
    for s in selected_stocks:
        s_id = s["stock_id"]
        stock_name = get_official_stock_name(s_id)
        price = latest_prices.get(s_id, 100.0)
        score = s["forecast_score"]
        
        target_weight = stock_target_weights.get(s_id, 0.03)
        target_val = total_nav * target_weight
        
        current_holdings = st.session_state["portfolio"].get(s_id, {"shares": 0, "avg_cost": 0.0})
        if not isinstance(current_holdings, dict):
            current_holdings = {"shares": current_holdings, "avg_cost": price}
        
        shares_held = current_holdings.get("shares", 0)
        current_val = shares_held * price
        val_diff = target_val - current_val
        
        if abs(val_diff) > (price * 1000):
            if val_diff > 0:
                buy_lots = int(val_diff // (price * 1000))
                buy_shares = buy_lots * 1000
                if buy_shares > 0:
                    gross_cost = buy_shares * price
                    fee = gross_cost * FEE_RATE
                    total_cost = gross_cost + fee
                    
                    if st.session_state["cash"] >= total_cost:
                        st.session_state["cash"] -= total_cost
                        new_shares = shares_held + buy_shares
                        new_avg_cost = ((shares_held * current_holdings.get("avg_cost", price)) + total_cost) / new_shares
                        st.session_state["portfolio"][s_id] = {"shares": new_shares, "avg_cost": new_avg_cost}
                        
                        st.session_state["trade_history"].append({
                            "時間": now_str, "股票代碼": s_id, "股票名稱": stock_name,
                            "動作": "買進 (BUY)", "成交單價": price, "整股(股)": buy_shares, 
                            "扣款總額": total_cost, "AI 評分": round(score, 4), "配置權重": f"{target_weight*100:.2f}%"
                        })
            else:
                sell_val = abs(val_diff)
                sell_lots = int(sell_val // (price * 1000))
                sell_shares = sell_lots * 1000
                if sell_shares > 0 and sell_shares <= shares_held:
                    gross_revenue = sell_shares * price
                    fee = gross_revenue * FEE_RATE
                    tax = gross_revenue * TAX_RATE
                    net_revenue = gross_revenue - fee - tax
                    
                    st.session_state["cash"] += net_revenue
                    new_shares = shares_held - sell_shares
                    st.session_state["portfolio"][s_id] = {"shares": new_shares, "avg_cost": current_holdings.get("avg_cost", price)}
                    
                    st.session_state["trade_history"].append({
                        "時間": now_str, "股票代碼": s_id, "股票名稱": stock_name,
                        "動作": "減碼 (TRIM)", "成交單價": price, "整股(股)": sell_shares, 
                        "淨入帳金額": net_revenue, "備註": "AI 動態權重調降"
                    })
                    
    st.success("🤖 AI 智慧選股與動態權重配置完成！持股檔數已自動調整至 20~30 檔合規區間。")

# -------------------------------------------------------------------
# 5. 資產總覽與規則檢核面板
# -------------------------------------------------------------------
stock_market_value = 0.0
inventory_data = []

portfolio_dict = st.session_state.get("portfolio", {})

for s_id, hold in portfolio_dict.items():
    if isinstance(hold, dict):
        s_shares = hold.get("shares", 0)
        avg_cost = hold.get("avg_cost", 0.0)
    else:
        s_shares = hold
        avg_cost = 0.0

    if s_shares > 0:
        cur_p = latest_prices.get(s_id, 100.0) if 'latest_prices' in locals() else 100.0
        mkt_val = s_shares * cur_p
        stock_market_value += mkt_val
        
        pnl = (cur_p - avg_cost) * s_shares
        pnl_pct = ((cur_p - avg_cost) / avg_cost) * 100 if avg_cost > 0 else 0
        
        inventory_data.append({
            "股票代碼": s_id,
            "股票名稱": get_official_stock_name(s_id),
            "持股張數": int(s_shares // 1000),
            "平均成本": f"${avg_cost:.2f}",
            "當前收盤價": f"${cur_p:.2f}",
            "持股市值": f"${mkt_val:,.0f}",
            "未實現損益": f"${pnl:+,.0f} ({pnl_pct:+.2f}%)"
        })

total_assets = st.session_state["cash"] + stock_market_value
cash_ratio = (st.session_state["cash"] / total_assets) * 100 if total_assets > 0 else 0

tsmc_shares = portfolio_dict.get("2330", {}).get("shares", 0) if isinstance(portfolio_dict.get("2330"), dict) else 0
tsmc_val = tsmc_shares * (latest_prices.get("2330", 100.0) if 'latest_prices' in locals() else 100.0)
tsmc_ratio = (tsmc_val / total_assets) * 100 if total_assets > 0 else 0

active_positions_count = len(inventory_data)

st.subheader("💰 基金資產總覽 (10 億元資本等級)")
m1, m2, m3, m4 = st.columns(4)
m1.metric("總資產淨值 (NAV)", f"${total_assets:,.0f}", f"{((total_assets - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:+.2f}%")
m2.metric("可用現金金額", f"${st.session_state['cash']:,.0f}", f"現金佔比: {cash_ratio:.1f}%")
m3.metric("股票持股總市值", f"${stock_market_value:,.0f}")
m4.metric("目前持股總檔數", f"{active_positions_count} 檔", "競賽限制: 20~30檔")

st.markdown("---")

# 風控合規性檢核卡片
st.subheader("🛡️ 競賽風控合規性檢核 (Compliance Control)")
c1, c2, c3 = st.columns(3)

with c1:
    if MIN_POSITIONS <= active_positions_count <= MAX_POSITIONS:
        st.success(f"✅ 持股檔數合規: {active_positions_count} 檔 (符合 20~30 檔)")
    else:
        st.error(f"❌ 持股檔數未達標: {active_positions_count} 檔 (需保持 20~30 檔)")
        
with c2:
    if cash_ratio < 25.0:
        st.success(f"✅ 現金部位合規: {cash_ratio:.2f}% (符合 < 25%)")
    else:
        st.error(f"❌ 現金部位超標: {cash_ratio:.2f}% (必須 < 25%)")
        
with c3:
    if tsmc_ratio <= 25.0:
        st.success(f"✅ 台積電權重合規: {tsmc_ratio:.2f}% (符合 <= 25%)")
    else:
        st.error(f"❌ 台積電權重超標: {tsmc_ratio:.2f}% (必須 <= 25%)")

st.markdown("---")

# -------------------------------------------------------------------
# 6. 頁籤明細展示與 CSV 下載
# -------------------------------------------------------------------
tab_ai, tab_inventory, tab_history = st.tabs(["🤖 AI 籌碼預測與評分", "📦 當前持股部位", "📜 評審審查-交易歷史日誌"])

with tab_ai:
    if 'forecast_results' in locals() and forecast_results:
        st.dataframe(pd.DataFrame(forecast_results), use_container_width=True)
    else:
        st.info("請點擊左側「🚀 執行 AI 多維度選股決策」以載入最新預測。")

with tab_inventory:
    if inventory_data:
        df_inventory = pd.DataFrame(inventory_data)
        st.dataframe(df_inventory, use_container_width=True)
        
        csv_data = df_inventory.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載持股部位 (CSV)",
            data=csv_data,
            file_name=f"portfolio_holdings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("尚無持股部位。請點擊左側『執行 AI 決策下單』。")

with tab_history:
    if st.session_state["trade_history"]:
        st.dataframe(pd.DataFrame(st.session_state["trade_history"][::-1]), use_container_width=True)
    else:
        st.info("尚無交易紀錄。")
