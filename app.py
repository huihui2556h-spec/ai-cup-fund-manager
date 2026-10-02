import streamlit as st
import pandas as pd
import plotly.express as px

from src.data_loader.finmind_loader import FinMindDataLoader
from src.models.dynamic_forecast import ai_dynamic_forecast
from src.optimizer.portfolio_opt import PortfolioOptimizer

# 1. 頁面配置
st.set_page_config(
    page_title="AI Agent Fund Manager",
    page_icon="📈",
    layout="wide"
)

st.title("🤖 AI CUP 2026 玉山人工智慧挑戰賽 - AI Agent 基金經理人儀表板")
st.markdown("---")

# 2. 側邊欄設定
st.sidebar.header("⚙️ 系統參數設定")
stock_input = st.sidebar.text_input("輸入分析股票代碼 (用逗號分開)", "2330, 2317, 2454")
target_stocks = [s.strip() for s in stock_input.split(",") if s.strip()]

run_button = st.sidebar.button("🚀 執行 AI 分析與投資組合最佳化", type="primary")

# 3. 初始化模組
@st.cache_resource
def get_components():
    loader = FinMindDataLoader()
    optimizer = PortfolioOptimizer()
    return loader, optimizer

loader, optimizer = get_components()

# 4. 執行預測邏輯
if run_button or "forecast_results" not in st.session_state:
    with st.spinner("正在讀取 FinMind 即時籌碼與股價數據，進行 AI 預測中..."):
        forecast_results = []
        for stock_id in target_stocks:
            res = ai_dynamic_forecast(stock_id, loader=loader)
            forecast_results.append(res)
        st.session_state["forecast_results"] = forecast_results

forecast_results = st.session_state.get("forecast_results", [])

# 5. 顯示 AI 預測摘要卡片
st.subheader("📊 AI 預測與籌碼訊號分析")
if forecast_results:
    cols = st.columns(len(forecast_results))
    benchmark_weights = {}
    equal_weight = round(1.0 / len(target_stocks), 2) if target_stocks else 0

    for idx, res in enumerate(forecast_results):
        stock_id = res["stock_id"]
        score = res["forecast_score"]
        signal = res["signal"]
        details = res.get("analysis_details", {})
        
        benchmark_weights[stock_id] = equal_weight

        with cols[idx]:
            st.metric(
                label=f"股票代號: {stock_id}",
                value=f"{score:.4f}",
                delta=f"訊號: {signal}"
            )
            st.write(f"• 動量分數: `{details.get('momentum_score', 0)}`")
            st.write(f"• 籌碼 Z-Score: `{details.get('chip_z_score', 0)}`")
            st.write(f"• 年化波動度: `{details.get('annual_volatility', 0)}`")

st.markdown("---")

# 6. 投資組合權重分配
st.subheader("⚖️ 投資組合最佳化配置 (Portfolio Allocation)")
col_left, col_right = st.columns([1, 1])

if forecast_results:
    final_portfolio = optimizer.optimize_weights(forecast_results, benchmark_weights)
    
    df_weights = pd.DataFrame([
        {"股票代碼": k, "建議配置權重 (%)": round(v * 100, 2)}
        for k, v in final_portfolio.items()
    ])

    with col_left:
        st.write("##### 權重分配表")
        st.dataframe(df_weights, use_container_width=True)

    with col_right:
        fig_pie = px.pie(
            df_weights,
            names="股票代碼",
            values="建議配置權重 (%)",
            title="最佳化權重比例圖",
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

st.markdown("---")

# 7. 個股數據明細
st.subheader("📈 個股歷史數據與籌碼趨勢驗證")
selected_stock = st.selectbox("選擇要檢視詳細籌碼與股價圖表的股票:", target_stocks if target_stocks else ["2330"])

if selected_stock:
    df_price = loader.get_stock_price(selected_stock)
    df_chips = loader.get_institutional_chips(selected_stock)

    tab1, tab2 = st.tabs(["📉 股價走勢圖", "🏦 三大法人買賣超數據"])

    with tab1:
        if not df_price.empty and "close" in df_price.columns:
            fig_line = px.line(df_price, x="date", y="close", title=f"{selected_stock} 歷史收盤價走勢")
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("尚無股價歷史數據。")

    with tab2:
        if not df_chips.empty:
            st.dataframe(df_chips, use_container_width=True)
        else:
            st.info("尚無籌碼數據。")
