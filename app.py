import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime

# 假設您的專案結構有這些模組，若無請依實際情況調整匯入路徑
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

st.title("💼 AI Agent 基金經理人 (奇摩價格 + FinMind 籌碼 AI 智慧投資)")
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

# 評分門檻滑桿
score_threshold = st.sidebar.slider("AI 買進評分門檻", min_value=0.0, max_value=1.0, value=0.45, step=0.01)

col_btn1, col_btn2 = st.sidebar.columns(2)
run_ai_btn = col_btn1.button("🚀 執行 AI 多維度選股決策", type="primary")
reset_btn = col_btn2.button("🔄 重置十億帳戶")

if reset_btn:
    st.session_state["cash"] = INITIAL_CAPITAL
    st.session_state["portfolio"] = {}
    st.session_state["trade_history"] = []
    st.sidebar.success("帳戶已重置為 10 億元初始資金！")

# -------------------------------------------------------------------
# 3. 安全的 API 資料獲取與快取處理 (防止 TypeError 崩潰)
# -------------------------------------------------------------------
@st.cache_resource
def get_loader():
    return FinMindDataLoader()

loader = get_loader()

@st.cache_resource(show_spinner=False)
def get_forecast_cached(stock_id):
    """安全呼叫 AI 預測模型，防止發生 TypeError 導致網頁崩潰"""
    try:
        # 呼叫預測模型 (不傳遞無法序列化的 loader 至參數快取)
        res = ai_dynamic_forecast(stock_id, loader=loader)
        if not isinstance(res, dict):
            return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": "回傳非字典格式"}
        return res
    except Exception as e:
        print(f"[系統日誌] 股票 {stock_id} 預測發生錯誤: {e}")
        # 出錯時給予預設值，確保程式能繼續跑完剩下的股票
        return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": str(e)}

# -------------------------------------------------------------------
# 4. 執行 AI 決策下單邏輯
# -------------------------------------------------------------------
if run_ai_btn:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    forecast_results = []
    latest_prices = {}
    
    # 建立進度條
    progress_bar = st.progress(0, text="正在載入 150 檔股票 AI 預測資料與即時價格...")
    
    for i, stock_id in enumerate(target_stocks):
        # 1. 取得預測分數
        res = get_forecast_cached(stock_id)
        score = res.get("forecast_score", 0.5) if isinstance(res, dict) else 0.5
        res["forecast_score"] = score
        forecast_results.append(res)
        
        # 2. 取得最新價格
        try:
            df_p = loader.get_stock_price(stock_id)
            if df_p is not None and not df_p.empty and "close" in df_p.columns:
                latest_prices[stock_id] = float(df_p["close"].iloc[-1])
            else:
                latest_prices[stock_id] = 100.0  # 預設價格
        except Exception:
            latest_prices[stock_id] = 100.0
            
        # 避免密集請求被 API 阻擋，微停頓
        time.sleep(0.05) 
        
        # 更新進度條
        progress_bar.progress((i + 1) / len(target_stocks), text=f"已處理 {stock_id} ({i+1}/{len(target_stocks)})")
        
    progress_bar.empty() # 隱藏進度條

    # --- 依分數排序並篩選前 20~30 檔 ---
    sorted_stocks = sorted(forecast_results, key=lambda x: x["forecast_score"], reverse=True)
    
    # 先濾出有大於等於「買進門檻」的強勢股
    qualified_stocks = [s for s in sorted_stocks if s["forecast_score"] >= score_threshold]
    
    # 取最多 MAX_POSITIONS (30檔)
    selected_stocks = qualified_stocks[:MAX_POSITIONS]
    
    if len(selected_stocks) < MIN_POSITIONS:
        st.warning(f"⚠️ 符合買進門檻 ({score_threshold}) 的股票僅有 {len(selected_stocks)} 檔，未達競賽 {MIN_POSITIONS} 檔下限。系統將自動補齊至最低門檻。")
        # 如果不夠 20 檔，強制補齊前 20 名以符合參賽規定
        selected_stocks = sorted_stocks[:MIN_POSITIONS]

    # --- 執行下單與資產重新分配 ---
    current_stock_val = sum(
        st.session_state["portfolio"].get(s["stock_id"], {}).get("shares", 0) * latest_prices.get(s["stock_id"], 0)
        for s in selected_stocks
    )
    total_nav = st.session_state["cash"] + current_stock_val
    
    target_stock_allocation_ratio = 0.90 # 預留 10% 現金
    num_selected = len(selected_stocks)
    
    # 建立這次要買的標的清單 ID
    selected_ids = [s["stock_id"] for s in selected_stocks]
    
    # 1. 強制平倉邏輯 (若持股跌破門檻，或不在本次精選名單中，則賣出)
    for s_id in list(st.session_state["portfolio"].keys()):
        current_holdings = st.session_state["portfolio"][s_id]
        shares_held = current_holdings["shares"]
        if shares_held > 0 and s_id not in selected_ids:
            price = latest_prices.get(s_id, 100.0)
            gross_revenue = shares_held * price
            fee = gross_revenue * FEE_RATE
            tax = gross_revenue * TAX_RATE
            net_revenue = gross_revenue - fee - tax
            
            st.session_state["cash"] += net_revenue
            st.session_state["portfolio"][s_id] = {"shares": 0, "avg_cost": 0.0}
            st.session_state["trade_history"].append({
                "時間": now_str, "股票代碼": s_id, "動作": "停損/平倉 (SELL)", 
                "成交單價": price, "整股(股)": shares_held, 
                "淨入帳金額": net_revenue, "備註": "未達 AI 門檻"
            })
    
    # 2. 建倉/加碼邏輯
    for res in selected_stocks:
        s_id = res["stock_id"]
        price = latest_prices.get(s_id, 100.0)
        score = res["forecast_score"]
        
        max_weight = TSMC_WEIGHT_LIMIT if s_id == "2330" else OTHER_WEIGHT_LIMIT
        max_allowed_val = total_nav * max_weight
        
        current_holdings = st.session_state["portfolio"].get(s_id, {"shares": 0, "avg_cost": 0.0})
        shares_held = current_holdings["shares"]
        
        target_val = min(max_allowed_val, (total_nav * target_stock_allocation_ratio) / num_selected)
        
        if target_val > (shares_held * price):
            buy_val_needed = target_val - (shares_held * price)
            buy_lots = int(buy_val_needed // (price * 1000))
            buy_shares = buy_lots * 1000
            
            if buy_shares > 0:
                gross_cost = buy_shares * price
                fee = gross_cost * FEE_RATE
                total_cost = gross_cost + fee
                
                if st.session_state["cash"] >= total_cost:
                    st.session_state["cash"] -= total_cost
                    new_shares = shares_held + buy_shares
                    new_avg_cost = ((shares_held * current_holdings["avg_cost"]) + total_cost) / new_shares
                    st.session_state["portfolio"][s_id] = {"shares": new_shares, "avg_cost": new_avg_cost}
                    
                    st.session_state["trade_history"].append({
                        "時間": now_str, "股票代碼": s_id, "動作": "買進 (BUY)", 
                        "成交單價": price, "整股(股)": buy_shares, 
                        "扣款總額": total_cost, "AI 評分": round(score, 4)
                    })
                    
    st.success("🤖 AI 交易決策執行完成！已根據 AI 評分門檻完成資產重分配。")

# -------------------------------------------------------------------
# 5. 資產總覽與規則檢核面板
# -------------------------------------------------------------------
stock_market_value = 0.0
inventory_data = []

for s_id, hold in st.session_state["portfolio"].items():
    s_shares = hold["shares"]
    if s_shares > 0:
        cur_p = latest_prices.get(s_id, 100.0) if 'latest_prices' in locals() else 0.0
        mkt_val = s_shares * cur_p
        stock_market_value += mkt_val
        
        pnl = (cur_p - hold["avg_cost"]) * s_shares
        pnl_pct = ((cur_p - hold["avg_cost"]) / hold["avg_cost"]) * 100 if hold["avg_cost"] > 0 else 0
        
        inventory_data.append({
            "股票代碼": s_id,
            "持股張數": int(s_shares // 1000),
            "平均成本": f"${hold['avg_cost']:.2f}",
            "當前收盤價": f"${cur_p:.2f}",
            "持股市值": f"${mkt_val:,.0f}",
            "未實現損益": f"${pnl:+,.0f} ({pnl_pct:+.2f}%)"
        })

total_assets = st.session_state["cash"] + stock_market_value
cash_ratio = (st.session_state["cash"] / total_assets) * 100 if total_assets > 0 else 0

tsmc_shares = st.session_state["portfolio"].get("2330", {}).get("shares", 0)
tsmc_val = tsmc_shares * (latest_prices.get("2330", 0.0) if 'latest_prices' in locals() else 0.0)
tsmc_ratio = (tsmc_val / total_assets) * 100 if total_assets > 0 else 0

active_positions_count = len(inventory_data)

st.subheader("💰 基金資產總覽 (10 億元資本等級)")
m1, m2, m3, m4 = st.columns(4)
m1.metric("總資產淨值 (NAV)", f"${total_assets:,.0f}", f"{((total_assets - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:+.2f}%")
m2.metric("可用現金金額", f"${st.session_state['cash']:,.0f}", f"現金佔比: {cash_ratio:.1f}%")
m3.metric("股票持股總市值", f"${stock_market_value:,.0f}")
m4.metric("目前持股總檔數", f"{active_positions_count} 檔", "競賽限制: 20~30檔")

st.markdown("---")

# 競賽規則檢核卡片
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
        # 顯示 DataFrame
        df_inventory = pd.DataFrame(inventory_data)
        st.dataframe(df_inventory, use_container_width=True)
        
        # 轉換為 CSV 格式 (加上 utf-8-sig 防止 Excel 中文亂碼)
        csv_data = df_inventory.to_csv(index=False).encode('utf-8-sig')
        
        # 建立下載按鈕
        st.download_button(
            label="📥 下載持股部位 (CSV)",
            data=csv_data,
            file_name=f"portfolio_holdings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("尚無持股部位。")

with tab_history:
    if st.session_state["trade_history"]:
        # 顯示反轉排序，最新的在最上面
        st.dataframe(pd.DataFrame(st.session_state["trade_history"][::-1]), use_container_width=True)
    else:
        st.info("尚無交易紀錄。")
