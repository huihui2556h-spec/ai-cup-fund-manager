from src.models.ai_agent_brain import get_ai_portfolio_decisions

# 在按鈕被點擊時：
if run_ai_btn:
    with st.spinner("🤖 AI 基金經理人正在深度分析 150 檔籌碼與總經數據並進行決策..."):
        # 1. 收集所有候選股的數據
        stocks_payload = []
        latest_prices = {}
        
        for stock_id in target_stocks:
            try:
                df_p = loader.get_stock_price(stock_id)
                cur_price = float(df_p["close"].iloc[-1]) if df_p is not None and not df_p.empty else 100.0
                latest_prices[stock_id] = cur_price
                
                chips = loader.get_institutional_chips(stock_id)
                net_buy = chips.get("institutional_net_buy", 0.0)
                
                stocks_payload.append({
                    "stock_id": stock_id,
                    "name": get_official_stock_name(stock_id),
                    "close_price": cur_price,
                    "net_buy": net_buy
                })
            except Exception:
                pass

        # 2. 呼叫 AI 大腦進行自主選股
        market_ctx = {
            "trade_date": datetime.now().strftime("%Y-%m-%d"),
            "target_count": len(target_stocks)
        }
        
        ai_decision_result = get_ai_portfolio_decisions(stocks_payload, market_ctx)
        
        # 3. 將 AI 決策對應到系統的選股清單與權重
        ai_decisions = ai_decision_result.get("decisions", [])
        
        forecast_results = []
        selected_stocks = []
        stock_target_weights = {}
        
        for d in ai_decisions:
            s_id = d["ticker"]
            weight = d["target_weight"]
            reason = d["reason"]
            
            # 套用風控上限
            if s_id == "2330":
                weight = min(weight, 0.25)
            else:
                weight = min(weight, 0.10)
                
            stock_target_weights[s_id] = weight
            selected_stocks.append({"stock_id": s_id, "forecast_score": 0.85}) # AI 自主選出給予高權重評分
            
            forecast_results.append({
                "stock_id": s_id,
                "stock_name": get_official_stock_name(s_id),
                "forecast_score": 0.85,
                "signal": "BUY",
                "reason": reason
            })

        # 確保檔數落在 20~30 檔合規區間
        if len(selected_stocks) < 20:
            # 若 AI 挑選不足 20 檔，自動從籌碼最強的標的補足
            sorted_by_chips = sorted(stocks_payload, key=lambda x: x["net_buy"], reverse=True)
            for s in sorted_by_chips:
                if len(selected_stocks) >= 20:
                    break
                s_id = s["stock_id"]
                if s_id not in [x["stock_id"] for x in selected_stocks]:
                    selected_stocks.append({"stock_id": s_id, "forecast_score": 0.70})
                    stock_target_weights[s_id] = 0.035
                    forecast_results.append({
                        "stock_id": s_id, "stock_name": get_official_stock_name(s_id),
                        "forecast_score": 0.70, "signal": "BUY", "reason": "AI 補充防禦與分散檔數"
                    })

        # 儲存至 Session
        st.session_state["forecast_results_state"] = forecast_results
        st.session_state["latest_prices_state"] = latest_prices
        
        st.success("🤖 AI 基金經理人已完成自主分析與投資組合配置！")
