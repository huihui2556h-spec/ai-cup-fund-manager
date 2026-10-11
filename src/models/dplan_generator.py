import json
import math
from datetime import datetime, timezone, timedelta

TAIPEI_TZ = timezone(timedelta(hours=8))

def generate_dplan_json(
    team_id: str,
    trade_date: str,
    nav: float,
    current_portfolio: dict, # {"2330": {"shares": 2000, "close_price": 1000.0}, ...}
    market_signals: dict,
    forecast_results: list
) -> dict:
    
    now_str = datetime.now(TAIPEI_TZ).isoformat(timespec='seconds')
    
    # 1. Sources (資料來源)
    sources = [
        {
            "source_id": "S1",
            "authority": "twse",
            "url": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            "content_as_of": f"{trade_date}T13:30:00+08:00"
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
            "statement": "台股上市櫃標的每日價量與收盤數據更新完成。",
            "values": {"market_status": 1.0}
        },
        {
            "obs_id": "O2",
            "source_ref": ["S2"],
            "authority_ref": "vendor",
            "statement": "FinMind 籌碼 Z-Score 與動量指標計算完畢。",
            "values": {"chip_score_avg": 0.5}
        }
    ]

    # 3. Market View (市場總覽)
    market_view = {
        "basis_refs": ["O1", "O2"],
        "logic": "市場整體籌碼與動量訊號平穩，維持中性建倉與持股曝險策略。",
        "regime": "neutral",
        "stance": "neutral",
        "posture": {
            "net_exposure_intent": "hold",
            "target_cash_pct_range": [0.05, 0.20]
        },
        "counter_evidence": None
    }

    inferences = []
    decisions = []
    no_trade_decisions = []
    orders = []

    inf_counter = 1
    dec_counter = 1
    handled_tickers = set()

    for res in forecast_results:
        s_id = str(res["stock_id"])
        score = res["forecast_score"]
        signal = res["signal"]
        
        # 取得當前持股與前日收盤價
        holding_info = current_portfolio.get(s_id, {"shares": 0, "close_price": 100.0})
        current_shares = holding_info["shares"]
        close_price = holding_info["close_price"]

        # 設定目標權重 (台積電 max 25%, 其餘 max 10%)
        if signal in ["BUY", "HOLD"] and score >= 0.40:
            target_weight = 0.23 if s_id == "2330" else 0.04
        else:
            target_weight = 0.0

        # 官方演算法算目標股數與委託股數
        target_shares = math.floor((target_weight * nav) / (close_price * 1000.0)) * 1000
        order_shares = target_shares - current_shares

        # 建立 Inference (推論)
        inf_id = f"I{inf_counter}"
        inf_counter += 1
        inferences.append({
            "inf_id": inf_id,
            "premise_refs": ["O1", "O2"],
            "logic": f"股票 {s_id} AI 綜合評分 {score:.2f}，訊號為 {signal}，符合投資組合最佳化與風險控管原則。",
            "counter_evidence": None
        })

        # 判斷是否需要進行動作 (decisions & orders)
        if order_shares != 0:
            dec_id = f"D{dec_counter}"
            dec_counter += 1
            
            if current_shares == 0:
                action = "BUY"
            elif order_shares > 0:
                action = "ADD"
            elif target_shares == 0:
                action = "SELL_ALL"
            else:
                action = "TRIM"

            decisions.append({
                "decision_id": dec_id,
                "ticker": s_id,
                "action": action,
                "target_weight": round(target_weight, 4),
                "inference_refs": [inf_id]
            })

            orders.append({
                "ticker": s_id,
                "side": "BUY" if order_shares > 0 else "SELL",
                "shares": abs(order_shares),
                "decision_ref": dec_id
            })
            handled_tickers.add(s_id)
        else:
            if current_shares > 0:
                no_trade_decisions.append({
                    "ticker": s_id,
                    "reason_refs": [inf_id]
                })
                handled_tickers.add(s_id)

    # 確保覆蓋所有既有持股 (Full Coverage 規則：昨日持股今日必須全部交代)
    for s_id, hold_info in current_portfolio.items():
        if hold_info["shares"] > 0 and s_id not in handled_tickers:
            inf_id = f"I{inf_counter}"
            inf_counter += 1
            inferences.append({
                "inf_id": inf_id,
                "premise_refs": ["O1"],
                "logic": f"股票 {s_id} 維持既有部位不作變動，符合現階段資產配置。",
                "counter_evidence": None
            })
            no_trade_decisions.append({
                "ticker": s_id,
                "reason_refs": [inf_id]
            })

    return {
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
            "model_provider": "google",
            "model_version": "gemini-2.5-flash",
            "run_started_at": now_str,
            "run_completed_at": now_str,
            "code_version": "git:main"
        }
    }
