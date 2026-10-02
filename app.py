import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

from src.data_loader.finmind_loader import FinMindDataLoader
from src.models.dynamic_forecast import ai_dynamic_forecast
from src.optimizer.portfolio_opt import PortfolioOptimizer
from src.models.dplan_generator import generate_dplan_json

# -------------------------------------------------------------------
# 1. 頁面配置與競賽風控常數宣告
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AI Agent 基金經理人 - AI CUP 2026",
    page_icon="💼",
    layout="wide"
)

INITIAL_CAPITAL = 1_000_000_000.0  # 10 億元初始資金
MIN_POSITIONS = 20                  # 最少持股檔數
MAX_POSITIONS = 30                  # 最多持股檔數
TSMC_WEIGHT_LIMIT = 0.25            # 2330.tw 上限 25%
OTHER_WEIGHT_LIMIT = 0.10           # 其餘個股上限 10%
MAX_CASH_RATIO = 0.25               # 現金部位每日必須 < 25%

FEE_RATE = 0.001425                 # 券商手續費 0.1425%
TAX_RATE = 0.003                    # 證券交易稅 0.3%

# 初始化 Session 狀態
if "cash" not in st.session_state:
    st.session_state["cash"] = INITIAL_CAPITAL
if "portfolio" not in st.session_state:
    # 格式: {stock_id: {"shares": 0, "avg_cost": 0.0}}
    st.session_state["portfolio"] = {}
if "trade_history" not in st.session_state:
    st.session_state["trade_history"] = []

st.title("💼 AI CUP 2026 - AI Agent 基金經理人 (競賽合規交易系統)")
st.caption("符合玉山挑戰賽規則：20~30 檔持股、個股上限限制、現金部位 < 25%、整股交易與稅費扣除")
st.markdown("---")

# -------------------------------------------------------------------
# 2. 側邊欄控制台
# -------------------------------------------------------------------
st.sidebar.header("⚙️ 競賽交易控制台")

# 預設提供至少 25 檔熱門台股以滿足持股下限
default_stocks = (
    "2330, 2317, 2454, 2308, 2382, 3231, 2356, 6669, 3017, 2379, "
    "2881, 2882, 2891, 2886, 5880, 1301, 1302, 2002, 2603, 2609, "
    "2615, 3008, 2408, 2303, 3711"
)
stock_input = st.sidebar.text_area("分析股票標的列表 (用逗號分開, 最少20檔)", default_stocks, height=120)
target_stocks = [s.strip() for s in stock_input.split(",") if s.strip()]

col_btn1, col_btn2 = st.sidebar.columns(2)
run_ai_btn = col_btn1.button("🚀 執行 AI 決策下單", type="primary")
reset_btn = col_btn2.button("🔄 重置十億帳戶")

if reset_btn:
    st.session_state["cash"] = INITIAL_CAPITAL
    st.session_state["portfolio"] = {}
    st.session_state["trade_history"] = []
    st.sidebar.success("帳戶已重置為 10 億元初始資金！")

@st.cache_resource
def get_loader():
    return FinMindDataLoader()

loader = get_loader()

# -------------------------------------------------------------------
# 3. 取得最新每日收盤價與 AI 預測分數
# -------------------------------------------------------------------
forecast_results = []
latest_prices = {}

for stock_id in target_stocks:
    res = ai_dynamic_forecast(stock_id, loader=loader)
    forecast_results.append(res)
    df_p = loader.get_stock_price(stock_id)
    if not df_p.empty and "close" in df_p.columns:
        latest_prices[stock_id] = float(df_p["close"].iloc[-1])
    else:
        latest_prices[stock_id] = 100.0  # 預設價格備用

# -------------------------------------------------------------------
# 4. 嚴格符合競賽規則的 AI 自動下單邏輯
# -------------------------------------------------------------------
if run_ai_btn:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. 篩選評分高於門檻的前 20~30 檔股票
    sorted_stocks = sorted(forecast_results, key=lambda x: x["forecast_score"], reverse=True)
    selected_stocks = sorted_stocks[:MAX_POSITIONS]
    
    if len(selected_stocks) < MIN_POSITIONS:
        st.error(f"⚠ 分析標的不足！競賽要求持股需在 {MIN_POSITIONS}~{MAX_POSITIONS} 檔，請至少輸入 20 檔股票。")
    else:
        # 2. 計算完整總淨值 (Total Net Asset Value)
        current_stock_val = sum(
            hold["shares"] * latest_prices.get(s_id, 0.0)
            for s_id, hold in st.session_state["portfolio"].items()
        )
        total_nav = st.session_state["cash"] + current_stock_val

        # 3. 確定目標股票權重分配 (保留 10% 現金以滿足 <25% 規範，其餘 90% 投入股票)
        target_stock_allocation_ratio = 0.90  
        num_selected = len(selected_stocks)
        
        # 進行下單計算
        for res in selected_stocks:
            s_id = res["stock_id"]
            price = latest_prices.get(s_id, 100.0)
            score = res["forecast_score"]
            signal = res["signal"]

            # 設定單檔持股淨值上限
            max_weight = TSMC_WEIGHT_LIMIT if s_id == "2330" else OTHER_WEIGHT_LIMIT
            max_allowed_val = total_nav * max_weight

            current_holdings = st.session_state["portfolio"].get(s_id, {"shares": 0, "avg_cost": 0.0})
            shares_held = current_holdings["shares"]

            if signal in ["BUY", "HOLD"] and score >= 0.40:
                # 計算目標建倉價值 (整股交易，1000 股為 1 張)
                target_val = min(max_allowed_val, (total_nav * target_stock_allocation_ratio) / num_selected)
                
                if target_val > (shares_held * price):
                    buy_val_needed = target_val - (shares_held * price)
                    # 只能買整張 (1,000 股)
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
                                "成交單價": price, "交易數量(張)": buy_lots, "整股(股)": buy_shares,
                                "成交金額": gross_cost, "手續費": fee, "證交稅": 0.0,
                                "扣款總額": total_cost, "AI 評分": score
                            })

            elif signal == "SELL" and shares_held > 0:
                sell_lots = int(shares_held // 1000)
                sell_shares = sell_lots * 1000
                
                if sell_shares > 0:
                    gross_revenue = sell_shares * price
                    fee = gross_revenue * FEE_RATE
                    tax = gross_revenue * TAX_RATE
                    net_revenue = gross_revenue - fee - tax

                    st.session_state["cash"] += net_revenue
                    st.session_state["portfolio"][s_id] = {"shares": 0, "avg_cost": 0.0}

                    st.session_state["trade_history"].append({
                        "時間": now_str, "股票代碼": s_id, "動作": "賣出 (SELL)",
                        "成交單價": price, "交易數量(張)": sell_lots, "整股(股)": sell_shares,
                        "成交金額": gross_revenue, "手續費": fee, "證交稅": tax,
                        "淨入帳金額": net_revenue, "AI 評分": score
                    })

        st.success("🤖 AI 交易決策執行完成！已根據每日收盤價、整股買賣與扣除稅費完成配置。")

# -------------------------------------------------------------------
# 5. 資產總覽與規則檢核面板
# -------------------------------------------------------------------
stock_market_value = 0.0
inventory_data = []

for s_id, hold in st.session_state["portfolio"].items():
    s_shares = hold["shares"]
    if s_shares > 0:
        cur_p = latest_prices.get(s_id, 0.0)
        mkt_val = s_shares * cur_p
        stock_market_value += mkt_val
        pnl = (cur_p - hold["avg_cost"]) * s_shares
        pnl_pct = ((cur_p - hold["avg_cost"]) / hold["avg_cost"]) * 100 if hold["avg_cost"] > 0 else 0
        
        inventory_data.append({
            "股票代碼": s_id, "持股張數": int(s_shares // 1000), "持股總股數": s_shares,
            "平均成本": f"${hold['avg_cost']:.2f}", "當前收盤價": f"${cur_p:.2f}",
            "持股市值": f"${mkt_val:,.0f}", "未實現損益": f"${pnl:+,.0f} ({pnl_pct:+.2f}%)"
        })

total_assets = st.session_state["cash"] + stock_market_value
cash_ratio = (st.session_state["cash"] / total_assets) * 100 if total_assets > 0 else 0
tsmc_shares = st.session_state["portfolio"].get("2330", {}).get("shares", 0)
tsmc_val = tsmc_shares * latest_prices.get("2330", 0.0)
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
        st.success(f"✅ 持股檔數合規: {active_positions_count} 檔 (符合 20~30 檔限制)")
    else:
        st.warning(f"⚠️ 持股檔數未達標: {active_positions_count} 檔 (需保持 20~30 檔)")

with c2:
    if cash_ratio < 25.0:
        st.success(f"✅ 現金部位合規: {cash_ratio:.2f}% (符合 < 25% 限制)")
    else:
        st.error(f"❌ 現金部位超標: {cash_ratio:.2f}% (必須 < 25%)")

with c3:
    if tsmc_ratio <= 25.0:
        st.success(f"✅ 台積電持股合規: {tsmc_ratio:.2f}% (符合 <= 25% 限制)")
    else:
        st.error(f"❌ 台積電持股超標: {tsmc_ratio:.2f}% (必須 <= 25%)")

st.markdown("---")

# -------------------------------------------------------------------
# 6. 頁籤明細展示 (AI 預測、庫存、交易歷史)
# -------------------------------------------------------------------
tab_report, tab_inventory, tab_history = st.tabs(["📄 每日 Agent 決策報告與交易書導出", "📦 當前庫存與均價", "📜 歷史交易紀錄"])

with tab_report:
    st.write("##### 📄 競賽繳交專用：D-Plan JSON (Schema v4.2 規格)")
    
    # 填寫隊伍資訊與交易日期
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        team_id_input = st.text_input("競賽隊伍 ID (team_id)", value="TEAM_11515")
    with col_t2:
        trade_date_input = st.date_input("交易日期 (trade_date)").strftime("%Y-%m-%d")
    
    st.markdown("---")
    
    # 觸發生成 D-Plan JSON
    if st.button("🔨 產出合規 D-Plan JSON 檔案", type="primary"):
        # 整理當前持股資訊供算價與覆蓋率檢核
        portfolio_for_dplan = {}
        for s_id, hold in st.session_state["portfolio"].items():
            if hold["shares"] > 0:
                portfolio_for_dplan[s_id] = {
                    "shares": hold["shares"],
                    "close_price": latest_prices.get(s_id, 100.0)
                }

        # 呼叫 generate_dplan_json 函數
        dplan_obj = generate_dplan_json(
            team_id=team_id_input,
            trade_date=trade_date_input,
            nav=total_assets,
            current_portfolio=portfolio_for_dplan,
            market_signals={},
            forecast_results=forecast_results
        )
        
        json_str = json.dumps(dplan_obj, indent=2, ensure_ascii=False)
        filename = f"D-Plan_{team_id_input}_{trade_date_input}.json"
        
        st.success(f"✅ 已成功生成符合 Schema v4.2 規範之檔案：`{filename}`")
        
        # 提供即時下載與 JSON 結構預覽
        st.download_button(
            label=f"📥 點此下載 JSON 繳交檔 ({filename})",
            data=json_str,
            file_name=filename,
            mime="application/json"
        )
        
        st.write("##### 🔍 D-Plan JSON 內容即時預覽：")
        st.json(dplan_obj)

with tab_inventory:
    st.write("##### 📦 當前帳戶持股與成本發明細")
    if inventory_data:
        st.dataframe(pd.DataFrame(inventory_data), use_container_width=True)
    else:
        st.info("目前尚無任何股票持股，請先點選側邊欄的『🚀 執行 AI 決策下單』。")

with tab_history:
    st.write("##### 📜 歷史下單與交易紀錄")
    if st.session_state["trade_history"]:
        st.dataframe(pd.DataFrame(st.session_state["trade_history"]), use_container_width=True)
    else:
        st.info("目前尚無歷史交易紀錄。")
