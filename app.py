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

# 引入 FinMind 與 AI 預測/大腦模組
try:
    from src.data_loader.finmind_loader import FinMindDataLoader
    from src.models.dynamic_forecast import ai_dynamic_forecast
    from src.models.ai_agent_brain import get_ai_portfolio_decisions
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

st.title("💼 AI Agent 基金經理人 (Gemini LLM 自主決策 + FinMind 籌碼分析)")
st.caption("符合玉山挑戰賽規則：20~30 檔持股、個股上限限制、現金部位 < 25%、整股交易與稅費扣除")
st.markdown("---")

# -------------------------------------------------------------------
# 2. 側邊欄控制台
# -------------------------------------------------------------------
st.sidebar.header("⚙️ AI 智慧策略面板")

if dynamic_stock_list:
    default_stocks = ", ".join(str(s) for s in dynamic_stock_list)
else:
    default_stocks = "2330, 2454, 2317, 2881, 2882"

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

@st.cache_data(ttl=3600, show_spinner=False)
def get_forecast_cached(stock_id):
    try:
        res = ai_dynamic_forecast(stock_id, loader=loader)
        if not isinstance(res, dict):
            return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": "回傳非字典格式"}
        return res
    except Exception as e:
        return {"stock_id": stock_id, "forecast_score": 0.5, "signal": "HOLD", "error": str(e)}

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
        
        csv_files.sort(reverse=True)
        latest_file = csv_files[0]
        
        df = pd.read_csv(latest_file, encoding='utf-8-sig')
        if "交易日期" in df.columns and "Yahoo 代號" in df.columns and "收盤價" in df.columns:
            df = df.sort_values(by="交易日期", ascending=False)
            df_latest = df.drop_duplicates(subset=["Yahoo 代號"], keep="first")
            for _, row in df_latest.iterrows():
                ticker = str(row["Yahoo 代號"]).split(".")[0]
                prices_dict[ticker] = float(row["收盤價"])
    except Exception as e:
        pass
    return prices_dict

local_prices = load_latest_prices_from_csv()

# -------------------------------------------------------------------
# 4. 執行 AI 決策與部位調整邏輯 (結合 Gemini AI 大腦)
# -------------------------------------------------------------------
if "forecast_results_state" not in st.session_state:
    st.session_state["forecast_results_state"] = []

if run_ai_btn:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.spinner("🤖 AI 基金經理人 (Gemini) 正在深度分析 150 檔籌碼與市場數據..."):
        # 1. 收集所有標的數據供 AI 評估
        stocks_payload = []
        latest_prices = {}
        forecast_results = []
        
        for stock_id in target_stocks:
            cur_price = local_prices.get(stock_id, 100.0)
            latest_prices[stock_id] = cur_price
            
            # 同時結合傳統模型評分作為參考
            res = get_forecast_cached(stock_id)
            score = res.get("forecast_score", 0.5)
            
            try:
                chips = loader.get_institutional_chips(stock_id)
                net_buy = chips.get("institutional_net_buy", 0.0)
            except Exception:
                net_buy = 0.0
                
            stocks_payload.append({
                "stock_id": stock_id,
                "name": get_official_stock_name(stock_id),
                "close_price": cur_price,
                "net_buy": net_buy,
                "forecast_score": score
            })
            
            res["stock_name"] = get_official_stock_name(stock_id)
            forecast_results.append(res)

        # 2. 呼叫 Gemini AI 大腦進行自主選股與權重配置
        market_ctx = {
            "trade_date": datetime.now().strftime("%Y-%m-%d"),
            "target_count": len(target_stocks)
        }
        ai_decision_result = get_ai_portfolio_decisions(stocks_payload, market_ctx)
        ai_decisions = ai_decision_result.get("decisions", [])

        selected_stocks = []
        stock_target_weights = {}

        for d in ai_decisions:
            s_id = d["ticker"]
            weight = d.get("target_weight", 0.035)
            reason = d.get("reason", "AI 智慧選股")
            
            # 風控合規限制
            if s_id == "2330":
                weight = min(weight, TSMC_WEIGHT_LIMIT)
            else:
                weight = min(weight, OTHER_WEIGHT_LIMIT)
                
            stock_target_weights[s_id] = weight
            selected_stocks.append({"stock_id": s_id, "forecast_score": 0.85})

        # 若 AI 挑選檔數不足 20 檔，自動以籌碼面最強標的補齊至 20 檔
        if len(selected_stocks) < MIN_POSITIONS:
            sorted_by_chips = sorted(stocks_payload, key=lambda x: x["net_buy"], reverse=True)
            for s in sorted_by_chips:
                if len(selected_stocks) >= MIN_POSITIONS:
                    break
                s_id = s["stock_id"]
                if s_id not in [x["stock_id"] for x in selected_stocks]:
                    selected_stocks.append({"stock_id": s_id, "forecast_score": 0.70})
                    stock_target_weights[s_id] = 0.035

        # 超過 30 檔則截斷至 30 檔
        if len(selected_stocks) > MAX_POSITIONS:
            selected_stocks = selected_stocks[:MAX_POSITIONS]

        st.session_state["forecast_results_state"] = forecast_results
        st.session_state["latest_prices_state"] = latest_prices

        # 3. 計算 NAV 與執行下單交易
        current_stock_val = sum(
            st.session_state["portfolio"].get(s["stock_id"], {}).get("shares", 0) * latest_prices.get(s["stock_id"], 100.0)
            for s in selected_stocks
        )
        total_nav = st.session_state["cash"] + current_stock_val

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

        # 執行買進與加減碼
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
                        
    st.success("🤖 Gemini AI 基金經理人自主選股與動態權重配置完成！")

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
# 6. 頁籤明細展示與 CSV 下載
# -------------------------------------------------------------------
tab_ai, tab_inventory, tab_history = st.tabs(["🤖 AI 籌碼預測與評分", "📦 當前持股部位", "📜 評審審查-交易歷史日誌"])

with tab_ai:
    saved_forecasts = st.session_state.get("forecast_results_state", [])
    if saved_forecasts:
        df_ai = pd.DataFrame(saved_forecasts)
        if "forecast_score" in df_ai.columns:
            df_ai["forecast_score"] = df_ai["forecast_score"].round(3)
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

# -------------------------------------------------------------------
# 7. 玉山賽事 v4.3 規格 D-Plan 自動生成與下載
# -------------------------------------------------------------------
try:
    from src.models.dplan_generator import DPlanGenerator
    dplan_gen = DPlanGenerator(team_id="TEAM_042")
except ImportError:
    dplan_gen = None

st.sidebar.markdown("---")
st.sidebar.subheader("📄 玉山賽事 D-Plan 導出")

if dplan_gen and st.session_state.get("forecast_results_state"):
    today_date_str = datetime.now().strftime("%Y-%m-%d")
    
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
    
    curr_stock_val = sum(
        active_portfolio.get(s_id, {}).get("shares", 0) * saved_prices.get(s_id, 100.0)
        for s_id in active_portfolio
    )
    current_nav = st.session_state["cash"] + curr_stock_val
    
    sorted_s = sorted(saved_forecasts, key=lambda x: x["forecast_score"], reverse=True)
    top_stocks = sorted_s[:25]
    raw_scores = [s["forecast_score"] for s in top_stocks]
    s_sum = sum(raw_scores) if sum(raw_scores) > 0 else 1.0
    
    target_weights_map = {}
    for s in top_stocks:
        w = (s["forecast_score"] / s_sum) * 0.90
        target_weights_map[s["stock_id"]] = min(w, 0.25 if s["stock_id"] == "2330" else 0.10)

    try:
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
    except Exception as e:
        st.sidebar.error(f"D-Plan 生成失敗: {e}")
else:
    st.sidebar.info("請先點擊上方「🚀 執行 AI 多維度選股決策」，即可解鎖 D-Plan 匯出功能。")
