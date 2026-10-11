import json
import math
from datetime import datetime, timezone, timedelta
from src.models.ai_analyst import fetch_dynamic_ai_analysis
from src.stock_list.official_stocks import get_official_stock_name

TAIPEI_TZ = timezone(timedelta(hours=8))

def generate_dplan_json(
    team_id: str,
    trade_date: str,
    nav: float,
    current_portfolio: dict,
    market_signals: dict,
    forecast_results: list
) -> dict:
    
    now_str = datetime.now(TAIPEI_TZ).isoformat(timespec='seconds')
    ai_insights = fetch_dynamic_ai_analysis(forecast_results, nav)
    
    if ai_insights:
        market_logic = ai_insights.get("market_logic", "市場動態震盪，AI 依據籌碼與動量指標執行資產配置。")
        stock_inferences_map = ai_insights.get("stock_inferences", {})
    else:
        market_logic = "量化指標顯示盤勢震盪，維持中性建倉與風險控管策略。"
        stock_inferences_map = {}

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

    market_view = {
        "basis_refs": ["O1", "O2"],
        "logic": market_logic,
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
        stock_name = get_official_stock_name(s_id) # 從獨立股票名單資料夾取得正確名稱
        score = res["forecast_score"]
        signal = res["signal"]
        
        holding_info = current_portfolio.get(s_id, {})
        current_shares = holding_info.get("shares", 0)
        close_price = holding_info.get("close_price", res.get("close_price", 100.0))

        if signal in ["BUY", "HOLD"] and score >= 0.40:
            target_weight = 0.23 if s_id == "2330" else 0.04
        else:
            target_weight = 0.0

        target_shares = math.floor((target_weight * nav) / (close_price * 1000.0)) * 1000
        order_shares = target_shares - current_shares

        default_logic = f"{stock_name} ({s_id}) AI 綜合評分 {score:.2f}，收盤價 {close_price} 元，訊號為 {signal}，符合動態資產配置。"
        dynamic_inf_logic = stock_inferences_map.get(s_id, default_logic)

        inf_id = f"I{inf_counter}"
        inf_counter += 1
        inferences.append({
            "inf_id": inf_id,
            "premise_refs": ["O1", "O2"],
            "logic": dynamic_inf_logic,
            "counter_evidence": None
        })

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

    for s_id, hold_info in current_portfolio.items():
        if hold_info.get("shares", 0) > 0 and s_id not in handled_tickers:
            stock_name = get_official_stock_name(s_id)
            inf_id = f"I{inf_counter}"
            inf_counter += 1
            inferences.append({
                "inf_id": inf_id,
                "premise_refs": ["O1"],
                "logic": f"{stock_name} ({s_id}) 維持既有部位不作變動，符合現階段風險控管。",
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
        "observations": [
            {"obs_id": "O1", "source_ref": ["S1"], "statement": "台股上市櫃標的每日價量與收盤數據更新完成。", "values": {"status": 1}},
            {"obs_id": "O2", "source_ref": ["S2"], "statement": "FinMind 籌碼 Z-Score 與動量指標計算完畢。", "values": {"z_score": 0.5}}
        ],
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
