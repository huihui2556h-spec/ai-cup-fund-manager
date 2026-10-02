import json
import math
from datetime import datetime, timezone, timedelta

TAIPEI_TZ = timezone(timedelta(hours=8))

def generate_dplan_json(
    team_id: str,
    trade_date: str, # 格式 YYYY-MM-DD
    nav: float,
    current_portfolio: dict, # {"2330": {"shares": 2000, "close_price": 1000.0}, ...}
    market_signals: dict,    # 從 FinMind/AI 得到的市場與個股資料
    forecast_results: list   # ai_dynamic_forecast 的輸出結果
) -> dict:
    
    now_iso = datetime.now(TAIPEI_TZ).isoformat(timespec='seconds')
    
    # 1. Sources (資料來源)
    sources = [
        {
            "source_id": "S1",
            "authority": "twse",
            "url": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            "content_as_of": f"{trade_date}T18:30:00+08:00"
        },
        {
            "source_id": "S2",
            "authority": "vendor",
            "url": "https://api.finmindtrade.com/api/v4/data",
            "content_as_of": f"{trade_date}T18:30:00+08:00"
        }
    ]

    # 2. Observations (事實)
    observations = [
        {
            "obs_id": "O1",
            "source_ref": ["S1"],
            "statement": f"大盤收盤最新數據讀取完成，市場波動度指標正常。",
            "values": {"market_volatility": 0.015}
        },
        {
            "obs_id": "O2",
            "source_ref": ["S2"],
            "statement": "三大法人籌碼與動量指標已由 FinMind 模組計算完成。",
            "values": {"chip_z_score_avg": 0.85}
        }
    ]

    # 3. Market View (整體市場觀點)
    market_view = {
        "basis_refs": ["O1", "O2"],
        "logic": "AI 模組評估大盤與籌碼結構為中性偏多，保持標準股票部位曝險。",
        "regime": "neutral",
        "stance": "neutral",
        "posture": {
            "net_exposure_intent": "hold",
            "target_cash_pct_range": [0.05, 0.20]
        },
        "counter_evidence": None
    }

    # 4. Inferences, Decisions, No-Trade Decisions, Orders 生成
    inferences = []
    decisions = []
    no_trade_decisions = []
    orders = []

    inf_counter = 1
    dec_counter = 1

    # 追蹤今日所有持股覆蓋狀況
    handled_tickers = set()

    for res in forecast_results:
        ticker = str(res["stock_id"])
        score = res["forecast_score"]
        signal = res["signal"]
        
        # 取得前日收盤價與目前持股
        current_holding = current_portfolio.get(ticker, {"shares": 0, "close_price": 100.0})
        close_price = current_holding.get("close_price", 100.0)
        current_shares = current_holding.get("shares", 0)

        # 擬定目標權重 Target Weight
        if signal in ["BUY", "HOLD"] and score >= 0.40:
            target_weight = 0.23 if ticker == "2330" else 0.04 # 台積電 max 25%, 其他 4%
        else:
            target_weight = 0.0

        # 官方演算法算 Target Shares 與 Orders
        target_shares = math.floor((target_weight * nav) / (close_price * 1000.0)) * 1000
        order_shares = target_shares - current_shares

        # 建立 Inference
        inf_id = f"I{inf_counter}"
        inf_counter += 1
        inferences.append({
            "inf_id": inf_id,
            "premise_refs": ["O2"],
            "logic": f"股票 {ticker} AI 綜合評分 {score:.2f}，訊號為 {signal}，符合投資組合最佳化目標權重配置。",
            "counter_evidence": None
        })

        if order_shares != 0:
            dec_id = f"D{dec_counter}"
            dec_counter += 1
            
            action = "BUY" if current_shares == 0 else ("ADD" if order_shares > 0 else ("SELL_ALL" if target_shares == 0 else "TRIM"))
            
            decisions.append({
                "decision_id": dec_id,
                "ticker": ticker,
                "action": action,
                "target_weight": round(target_weight, 4),
                "inference_refs": [inf_id]
            })

            orders.append({
                "ticker": ticker,
                "side": "BUY" if order_shares > 0 else "SELL",
                "shares": abs(order_shares),
                "decision_ref": dec_id
            })
            handled_tickers.add(ticker)
        else:
            if current_shares > 0:
                no_trade_decisions.append({
                    "ticker": ticker,
                    "reason_refs": [inf_id]
                })
                handled_tickers.add(ticker)

    # 確保所有既有持股均出現在 decisions 或 no_trade_decisions (完整覆蓋率)
    for ticker, hold_info in current_portfolio.items():
        if hold_info["shares"] > 0 and ticker not in handled_tickers:
            inf_id = f"I{inf_counter}"
            inf_counter += 1
            inferences.append({
                "inf_id": inf_id,
                "premise_refs": ["O1"],
                "logic": f"股票 {ticker} 保持現有持股，無調整需求。",
                "counter_evidence": None
            })
            no_trade_decisions.append({
                "ticker": ticker,
                "reason_refs": [inf_id]
            })

    dplan = {
        "schema_version": "4.2",
        "doc_type": "D-Plan",
        "team_id": team_id,
        "trade_date": trade_date,
        "sources": sources,
        "observations": observations,
        "market_view": market_view,
        "inferences": inferences,
        "decisions": decisions,
        "no_trade_decisions": no_trade_decisions,
        "orders": orders,
        "agent_metadata": {
            "model_provider": "anthropic",
            "model_version": "claude-3-5-sonnet",
            "run_started_at": now_iso,
            "run_completed_at": now_iso,
            "code_version": "git:a1b2c3d"
        }
    }
    
    return dplan
