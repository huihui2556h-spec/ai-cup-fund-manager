mport json
import sys
import os
from datetime import datetime, timezone, timedelta

# 1. 確保專案根目錄加入路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 2. 標準第三方套件
import streamlit as st
import pandas as pd
import numpy as np

# 3. 專案內部模組匯入（乾淨不重複）
from src.data_loader.finmind_loader import FinMindDataLoader
from src.models.dynamic_forecast import ai_dynamic_forecast
from src.models.dplan_generator import generate_dplan_json

# -------------------------------------------------------------------
# 0. 官方指定 150 檔交易標的清單 (上市 100 檔 / 上櫃 50 檔)
# -------------------------------------------------------------------
LISTED_STOCKS_100 = [
    "2330", "2454", "2308", "2317", "3711", "2881", "2383", "2303", "2882", "3037",
    "2891", "1303", "2345", "2382", "2408", "7769", "2412", "2327", "6669", "3017",
    "2885", "2887", "2360", "2886", "2059", "6505", "2884", "2880", "2357", "2890",
    "2883", "3443", "3653", "2395", "2301", "6446", "4958", "2603", "5880", "1216",
    "3045", "2368", "3665", "4904", "3481", "2379", "1301", "1326", "3189", "3034",
    "2207", "2002", "2801", "2449", "1590", "3661", "6770", "3036", "2615", "2618",
    "8046", "2344", "3231", "2892", "3008", "2356", "2404", "6515", "3533", "2313",
    "2337", "5871", "3044", "3702", "1101", "2409", "6239", "2609", "2834", "6139",
    "2912", "4938", "2376", "5876", "1519", "2356", "6415", "6919", "2324", "2347",
    "1504", "7750", "1402", "1605", "2610", "6789", "1802", "8210", "2451", "2812", "2377"
]

OTC_STOCKS_50 = [
    "5274", "6223", "6488", "8299", "6274", "5347", "3293", "8069", "3529", "3081",
    "3260", "3105", "5289", "5536", "5483", "6147", "7734", "6187", "3264", "3324",
    "6510", "8358", "3374", "3131", "4749", "3491", "6121", "6548", "1785", "3363",
    "7828", "4979", "6182", "3163", "3211", "4966", "4991", "5903", "1815", "3680",
    "8415", "6290", "7751", "6023", "4772", "8932", "6584", "3227", "4123", "3718"
]

OFFICIAL_150_UNIVERSE = list(dict.fromkeys(LISTED_STOCKS_100 + OTC_STOCKS_50))

# -------------------------------------------------------------------
# 1. 頁面與風控參數配置
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AI Agent 基金經理人 - AI CUP 2026",
    page_icon="💼",
    layout="wide"
)

INITIAL_CAPITAL = 1_000_000_000.0  # 10 億元初始資金
MIN_POSITIONS = 20                  # 最少持股 20 檔
MAX_POSITIONS = 30                  # 最多持股 30 檔
TSMC_WEIGHT_LIMIT = 0.25            # 台積電 <= 25%
OTHER_WEIGHT_LIMIT = 0.10           # 其餘個股 <= 10%
MAX_CASH_RATIO = 0.25               # 現金部位每日 < 25%

FEE_RATE = 0.001425
TAX_RATE = 0.003

if "cash" not in st.session_state:
    st.session_state["cash"] = INITIAL_CAPITAL
if "portfolio" not in st.session_state:
    st.session_state["portfolio"] = {}
if "trade_history" not in st.session_state:
    st.session_state["trade_history"] = []

st.title("💼 AI Agent 基金經理人 (奇摩價格 + FinMind 籌碼 AI 智慧投資)")
st.caption("奇摩股市 API 抓取即時價格 + FinMind 抓取法人籌碼，結合多因子 AI 自動推理與下單風控")
st.markdown("---")

FINMIND_TOKEN = st.secrets.get("FINMIND_TOKEN", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiYWFyb24wNyIsImVtYWlsIjoiaHVpaHVpMjU1NmhAZ21haWwuY29tIiwidG9rZW5fdmVyc2lvbiI6MX0.BdgiGJOgolh7XdygpW4IUe_6i35KLenzNPTufGRpHVY")

@st.cache_resource
def get_loader():
    return FinMindDataLoader(api_token=FINMIND_TOKEN)

loader = get_loader()

@st.cache_data(ttl=1800)
def get_forecast_cached(stock_id: str, _loader):
    return ai_dynamic_forecast(stock_id, loader=_loader)

# -------------------------------------------------------------------
# 2. 側邊欄與 AI 決策驅動
# -------------------------------------------------------------------
st.sidebar.header("⚙️ AI 智慧策略面板")

universe_size = st.sidebar.slider("AI 掃描官方標的檔數", min_value=30, max_value=150, value=50, step=10)
score_threshold = st.sidebar.slider("AI 買進評分門檻", min_value=0.0, max_value=1.0, value=0.45, step=0.05)

col_btn1, col_btn2 = st.sidebar.columns(2)
run_ai_btn = col_btn1.button("🚀 執行 AI 多維度選股決策", type="primary")
reset_btn = col_btn2.button("🔄 重置十億帳戶")

if reset_btn:
    st.session_state["cash"] = INITIAL_CAPITAL
    st.session_state["portfolio"] = {}
    st.session_state["trade_history"] = []
    st.sidebar.success("帳戶已重置為 10 億元初始資金！")

# -------------------------------------------------------------------
# 3. 多維度 AI 掃描與決策執行
# -------------------------------------------------------------------
target_stocks = OFFICIAL_150_UNIVERSE[:universe_size]
forecast_results = []
latest_prices = {}

for stock_id in target_stocks:
    res = get_forecast_cached(stock_id, _loader=loader)
    res["authority"] = "tpex" if stock_id in OTC_STOCKS_50 else "twse"
    
    real_price = float(res.get("close_price", 100.0))
    latest_prices[stock_id] = real_price
    forecast_results.append(res)

if run_ai_btn:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 依 AI 綜合評分排序，挑選前 20~30 檔
    sorted_stocks = sorted(forecast_results, key=lambda x: x["forecast_score"], reverse=True)
    selected_stocks = sorted_stocks[:MAX_POSITIONS]
    
    if len(selected_stocks) < MIN_POSITIONS:
        st.error(f"⚠ 選取標的不足 {MIN_POSITIONS} 檔，請調低分數門檻或增加掃描檔數。")
    else:
        current_stock_val = sum(
            hold["shares"] * latest_prices.get(s_id, 0.0)
            for s_id, hold in st.session_state["portfolio"].items()
        )
        total_nav = st.session_state["cash"] + current_stock_val
        target_allocation_ratio = 0.90  # 90% 資金分配給股票，10% 留存現金
        num_selected = len(selected_stocks)
        
        for res in selected_stocks:
            s_id = res["stock_id"]
            price = latest_prices.get(s_id, 100.0)
            score = res["forecast_score"]
            signal = res["signal"]

            max_weight = TSMC_WEIGHT_LIMIT if s_id == "2330" else OTHER_WEIGHT_LIMIT
            max_allowed_val = total_nav * max_weight

            current_holdings = st.session_state["portfolio"].get(s_id, {"shares": 0, "avg_cost": 0.0})
            shares_held = current_holdings["shares"]

            if signal in ["BUY", "HOLD"] and score >= score_threshold:
                target_val = min(max_allowed_val, (total_nav * target_allocation_ratio) / num_selected)
                
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
                                "成交單價": price, "交易數量(張)": buy_lots, "整股(股)": buy_shares,
                                "成交金額": gross_cost, "扣款總額": total_cost, "AI 綜合評分": score, "AI 推理決策": res["logic"]
                            })

            elif (signal == "SELL" or score < score_threshold) and shares_held > 0:
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
                        "成交金額": gross_revenue, "淨入帳金額": net_revenue, "AI 綜合評分": score, "AI 推理決策": res["logic"]
                    })

        st.success("🤖 AI 多維度智慧決策完成！已結合奇摩價格與 FinMind 法人籌碼建構投資組合。")

# -------------------------------------------------------------------
# 4. 資產與風控檢核儀表板
# -------------------------------------------------------------------
stock_market_value = sum(
    hold["shares"] * latest_prices.get(s_id, 0.0)
    for s_id, hold in st.session_state["portfolio"].items()
)
inventory_data = []

for s_id, hold in st.session_state["portfolio"].items():
    s_shares = hold["shares"]
    if s_shares > 0:
        cur_p = latest_prices.get(s_id, 0.0)
        mkt_val = s_shares * cur_p
        pnl = (cur_p - hold["avg_cost"]) * s_shares
        pnl_pct = ((cur_p - hold["avg_cost"]) / hold["avg_cost"]) * 100 if hold["avg_cost"] > 0 else 0
        
        inventory_data.append({
            "股票代碼": s_id, "持股張數": int(s_shares // 1000), "持股總股數": s_shares,
            "平均成本": f"${hold['avg_cost']:.2f}", "當前收盤價 (奇摩)": f"${cur_p:.2f}",
            "持股市值": f"${mkt_val:,.0f}", "未實現損益": f"${pnl:+,.0f} ({pnl_pct:+.2f}%)"
        })

total_assets = st.session_state["cash"] + stock_market_value
cash_ratio = (st.session_state["cash"] / total_assets) * 100 if total_assets > 0 else 0
active_positions_count = len(inventory_data)

st.subheader("💰 基金資產總覽 (10 億元資本等級)")
m1, m2, m3, m4 = st.columns(4)
m1.metric("總資產淨值 (NAV)", f"${total_assets:,.0f}", f"{((total_assets - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:+.2f}%")
m2.metric("可用現金金額", f"${st.session_state['cash']:,.0f}", f"現金佔比: {cash_ratio:.1f}%")
m3.metric("股票持股總市值", f"${stock_market_value:,.0f}")
m4.metric("目前持股總檔數", f"{active_positions_count} 檔", "競賽限制: 20~30檔")

st.markdown("---")

tab_ai, tab_report, tab_inventory, tab_history = st.tabs([
    "🤖 奇摩+FinMind AI 綜合分析報告",
    "📄 D-Plan JSON 導出 (Schema 4.2)",
    "📦 當前庫存明細",
    "📜 歷史交易紀錄"
])

with tab_ai:
    st.write("##### 📊 官方 150 檔多因子 AI 決策與籌碼推理列表")
    df_forecast = pd.DataFrame(forecast_results)
    if not df_forecast.empty:
        st.dataframe(
            df_forecast[["stock_id", "authority", "close_price", "forecast_score", "signal", "logic"]].rename(columns={
                "stock_id": "股票代碼",
                "authority": "交易所類型",
                "close_price": "奇摩即時收盤價",
                "forecast_score": "AI 綜合評分",
                "signal": "交易訊號",
                "logic": "AI 綜合推理依據"
            }),
            use_container_width=True
        )

with tab_report:
    st.write("##### 📄 競賽繳交專用：D-Plan JSON (Schema v4.2 規格)")
    col_t1, col_t2 = st.columns(2)
    team_id_input = col_t1.text_input("競賽隊伍 ID (team_id)", value="TEAM_11515")
    trade_date_input = col_t2.date_input("交易日期 (trade_date)").strftime("%Y-%m-%d")
    
    if st.button("🔨 產出合規 D-Plan JSON 檔案", type="primary"):
        portfolio_for_dplan = {
            s_id: {"shares": hold["shares"], "close_price": latest_prices.get(s_id, 100.0)}
            for s_id, hold in st.session_state["portfolio"].items() if hold["shares"] > 0
        }

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
        st.download_button(
            label=f"📥 點此下載 JSON 繳交檔 ({filename})",
            data=json_str,
            file_name=filename,
            mime="application/json"
        )
        st.json(dplan_obj)

with tab_inventory:
    st.write("##### 📦 當前帳戶持股與成本明細")
    if inventory_data:
        st.dataframe(pd.DataFrame(inventory_data), use_container_width=True)
    else:
        st.info("目前尚無任何股票持股，請先點選側邊欄的『🚀 執行 AI 多維度選股決策』。")

with tab_history:
    st.write("##### 📜 歷史下單與交易紀錄 (包含 AI 推理依據)")
    if st.session_state["trade_history"]:
        st.dataframe(pd.DataFrame(st.session_state["trade_history"]), use_container_width=True)
    else:
        st.info("目前尚無歷史交易紀錄。")
