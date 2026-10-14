import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os
import glob
import json

# ==========================================
# 0. 引入官方 150 檔股票名稱對照模組與動態清單
# ==========================================
try:
    from src.stock_list.official_stocks import get_official_stock_name
    import src.stock_list.official_stocks as official_stocks_module
    
    if hasattr(official_stocks_module, "ESUN_OFFICIAL_150_STOCKS"):
        _data = official_stocks_module.ESUN_OFFICIAL_150_STOCKS
        dynamic_stock_list = list(_data.keys()) if isinstance(_data, dict) else list(_data)
    elif hasattr(official_stocks_module, "OFFICIAL_STOCKS"):
        _data = official_stocks_module.OFFICIAL_STOCKS
        dynamic_stock_list = list(_data.keys()) if isinstance(_data, dict) else list(_data)
    else:
        dynamic_stock_list = []
except ImportError:
    def get_official_stock_name(stock_id):
        return f"指定標的_{stock_id}"
    dynamic_stock_list = []

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

INITIAL_CAPITAL = 1_000_000_000.0  
MIN_POSITIONS = 20                 
MAX_POSITIONS = 30                 
TSMC_WEIGHT_LIMIT = 0.25           
OTHER_WEIGHT_LIMIT = 0.10          
MAX_CASH_RATIO = 0.25              
FEE_RATE = 0.001425                
TAX_RATE = 0.003                   

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

if dynamic_stock_list:
    default_stocks = ", ".join(str(s) for s in dynamic_stock_list)
else:
    default_stocks = "2330, 2454, 2317, 2881, 2882" # 簡化備案

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
# 3. 安全的 API 資料獲取與快取處理 (加入讀取本地 CSV 功能)
# -------------------------------------------------------------------
@st.cache_resource
def get_loader():
    return FinMindDataLoader()

loader = get_loader()

# 🛑 關鍵修復：把 cache_resource 改成 cache_data(ttl=3600)，每小時自動清除舊分數快取！
@st.cache_data(ttl=3600, show_spinner=False)
def get_forecast_cached(stock_id):
    try:
        res = ai_dynamic_forecast(stock_id, loader=loader)
        if not isinstance(res, dict):
            return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": "回傳非字典格式"}
        return res
    except Exception as e:
        return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": str(e)}

# 自動讀取 historical_data 抓最新收盤價
@st.cache_data(ttl=3600)
def load_latest_prices_from_csv():
    prices_dict = {}
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "src", "fetchers", "historical_data")
        if not os.path.exists(data_dir):
            return prices_dict
            
        csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
        if not csv_files:
            return prices_dict
        
        # 排序找到最新的年份 CSV
        csv_files.sort(reverse=True)
        latest_file = csv_files[0]
        
        df = pd.read_csv(latest_file, encoding='utf-8-sig')
        if "交易日期" in df.columns and "Yahoo 代號" in df.columns and "收盤價" in df.columns:
            # 確保照日期新到舊排序
            df = df.sort_values(by="交易日期", ascending=False)
            # 每一檔股票只留第一筆 (也就是最新的一天)
            df_latest = df.drop_duplicates(subset=["Yahoo 代號"], keep="first")
            for _, row in df_latest.iterrows():
                ticker = str(row["Yahoo 代號"]).split(".")[0] # 去掉 .TW
                prices_dict[ticker] = float(row["收盤價"])
    except Exception as e:
        pass
    return prices_dict

# 在每次網頁刷新時，取得最新的 CSV 價格字典
local_prices = load_latest_prices_from_csv()

# -------------------------------------------------------------------
# 4. 執行 AI 決策下單邏輯 (加入 session_state 持久化儲存)
# -------------------------------------------------------------------
if "forecast_results_state" not in st.session_state:
    st.session_state["forecast_results_state"] = []

if run_ai_btn:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    forecast_results = []
    latest_prices = {}
    
    progress_bar = st.progress(0, text="🤖 AI 正在進行多維度籌碼與波動慣性運算...")

    for i, stock_id in enumerate(target_stocks):
        res = get_forecast_cached(stock_id)
        score = res.get("forecast_score", 0.5) if isinstance(res, dict) else 0.5
        res["forecast_score"] = score
        res["stock_name"] = get_official_stock_name(stock_id)
        forecast_results.append(res)
        
        # 直接優先使用剛剛從 CSV 讀取到的真實價格，若找不到才預設 100
        latest_prices[stock_id] = local_prices.get(stock_id, 100.0)
            
        progress_bar.progress((i + 1) / len(target_stocks), text=f"正在分析: {get_official_stock_name(stock_id)} ({stock_id})")
        time.sleep(0.01) # 讓進度條順暢
        
    progress_bar.empty()

    st.session_state["forecast_results_state"] = forecast_results
    st.session_state["latest_prices_state"] = latest_prices

    sorted_stocks = sorted(forecast_results, key=lambda x: x["forecast_score"], reverse=True)
    selected_stocks = [s for s in sorted_stocks if s["forecast_score"] >= score_threshold]
    
    if len(selected_stocks) < MIN_POSITIONS:
        selected_stocks = sorted_stocks[:MIN_POSITIONS]
    elif len(selected_stocks) > MAX_POSITIONS:
        selected_stocks = selected_stocks[:MAX_POSITIONS]

    current_stock_val = sum(
        st.session_state["portfolio"].get(s["stock_id"], {}).get("shares", 0) * latest_prices.get(s["stock_id"], 100.0)
        for s in selected_stocks
    )
    total_nav = st.session_state["cash"] + current_stock_val

    raw_scores = [s["forecast_score"] for s in selected_stocks]
    score_sum = sum(raw_scores) if sum(raw_scores) > 0 else 1.0
    
    target_allocation_pool = 0.90
    stock_target_weights = {}
    
    for s in selected_stocks:
        s_id = s["stock_id"]
        weight = (s["forecast_score"] / score_sum) * target_allocation_pool
        if s_id == "2330":
            weight = min(weight, TSMC_WEIGHT_LIMIT)
        else:
            weight = min(weight, OTHER_WEIGHT_LIMIT)
        stock_target_weights[s_id] = weight

    selected_ids = [s["stock_id"] for s in selected_stocks]

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
                    
    st.success("🤖 AI 智慧選股與動態權重配置完成！")

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
        # 隨時從 CSV 讀取真實最新價
        cur_p = local_prices.get(s_id, 100.0) 
        mkt_val = s_shares * cur_p
        stock_market_value += mkt_val
        pnl = (cur_p - avg_cost) * s_shares
        pnl_pct = ((cur_p - avg_cost) / avg_cost) * 100 if avg_cost > 0 else 0
        
        inventory_data.append({
            "股票代碼": s_id, "股票名稱": get_official_stock_name(s_id),
            "持股張數": int(s_shares // 1000), "平均成本": f"${avg_cost:.2f}",
            "當前收盤價": f"${cur_p:.2f}", "持股市值": f"${mkt_val:,.0f}",
            "未實現損益": f"${pnl:+,.0f} ({pnl_pct:+.2f}%)"
        })

total_assets = st.session_state["cash"] + stock_market_value
cash_ratio = (st.session_state["cash"] / total_assets) * 100 if total_assets > 0 else 0

tsmc_shares = portfolio_dict.get("2330", {}).get("shares", 0) if isinstance(portfolio_dict.get("2330"), dict) else 0
# 台積電權重也是用真實報價算
tsmc_val = tsmc_shares * local_prices.get("2330", 100.0)
tsmc_ratio = (tsmc_val / total_assets) * 100 if total_assets > 0 else 0

active_positions_count = len(inventory_data)

st.subheader("💰 基金資產總覽 (10 億元資本等級)")
m1, m2, m3, m4 = st.columns(4)
m1.metric("總資產淨值 (NAV)", f"${total_assets:,.0f}", f"{((total_assets - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:+.2f}%")
m2.metric("可用現金金額", f"${st.session_state['cash']:,.0f}", f"現金佔比: {cash_ratio:.1f}%")
m3.metric("股票持股總市值", f"${stock_market_value:,.0f}")
m4.metric("目前持股總檔數", f"{active_positions_count} 檔", "競賽限制: 20~30檔")

st.markdown("---")

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
# 6. 頁籤明細展示與 CSV 下載 (加入 JSON 展開與四捨五入修復)
# -------------------------------------------------------------------
tab_ai, tab_inventory, tab_history = st.tabs(["🤖 AI 籌碼預測與評分", "📦 當前持股部位", "📜 評審審查-交易歷史日誌"])

with tab_ai:
    if 'forecast_results' in locals() and forecast_results:
        df_ai = pd.DataFrame(forecast_results)
        
        if "forecast_score" in df_ai.columns:
            df_ai["forecast_score"] = df_ai["forecast_score"].round(3)
            
        if "sub_scores" in df_ai.columns:
            sub_dicts = df_ai["sub_scores"].apply(lambda x: x if isinstance(x, dict) else {})
            sub_df = pd.DataFrame(sub_dicts.tolist())
            sub_df = sub_df.round(2)
            sub_df.columns = [f"子指標_{col}" for col in sub_df.columns]
            df_ai = pd.concat([df_ai.drop(columns=["sub_scores"]), sub_df], axis=1)

        st.dataframe(df_ai, use_container_width=True)
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

# 引入 D-Plan 生成器
try:
    from src.models.dplan_generator import DPlanGenerator
    dplan_gen = DPlanGenerator(team_id="TEAM_042") # 可依你的參賽隊伍 ID 修改
except ImportError:
    dplan_gen = None

# 在網頁側邊欄或頁籤中加入 D-Plan 導出按鈕
st.sidebar.markdown("---")
st.sidebar.subheader("📄 玉山賽事 D-Plan 導出")

if dplan_gen and 'forecast_results_state' in st.session_state and st.session_state["forecast_results_state"]:
    today_date_str = datetime.now().strftime("%Y-%m-%d")
    
    # 準備產生 D-Plan JSON
    active_portfolio = st.session_state.get("portfolio", {})
    saved_forecasts = st.session_state.get("forecast_results_state", [])
    saved_prices = st.session_state.get("latest_prices_state", {})
    
    market_payload = {
        "taiex": 23412.5,
        "taiex_chg_pct": -0.35,
        "sox_chg_pct": -0.80,
        "txf_night": 23290,
        "prices": saved_prices
    }
    
    # 計算當前 nav_tradable
    curr_stock_val = sum(
        active_portfolio.get(s_id, {}).get("shares", 0) * saved_prices.get(s_id, 100.0)
        for s_id in active_portfolio
    )
    current_nav = st.session_state["cash"] + curr_stock_val
    
    # 選出前 25 檔強勢股與目標權重
    sorted_s = sorted(saved_forecasts, key=lambda x: x["forecast_score"], reverse=True)
    top_stocks = sorted_s[:25]
    raw_scores = [s["forecast_score"] for s in top_stocks]
    s_sum = sum(raw_scores) if sum(raw_scores) > 0 else 1.0
    
    target_weights_map = {}
    for s in top_stocks:
        w = (s["forecast_score"] / s_sum) * 0.90
        target_weights_map[s["stock_id"]] = min(w, 0.25 if s["stock_id"] == "2330" else 0.10)

    # 生成 D-Plan 字典
    dplan_json_dict = dplan_gen.generate_dplan(
        trade_date=today_date_str,
        market_data=market_payload,
        portfolio=active_portfolio,
        nav_tradable=current_nav,
        selected_stocks=top_stocks,
        target_weights=target_weights_map,
        previous_holdings=active_portfolio
    )
    
    json_string = json.dumps(dplan_json_dict, ensure_ascii=False, indent=4)
    filename = f"D-Plan_TEAM_042_{today_date_str}.json"
    
    st.sidebar.download_button(
        label="📥 下載今日 D-Plan (v4.3 JSON)",
        data=json_string,
        file_name=filename,
        mime="application/json",
        type="primary"
    )
else:
    st.sidebar.info("請先點擊「🚀 執行 AI 多維度選股決策」，即可解鎖 D-Plan 匯出功能。")
