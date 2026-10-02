import json
from datetime import datetime, timezone, timedelta

TAIPEI_TZ = timezone(timedelta(hours=8))

def generate_dplan_json(team_id: str, trade_date: str, nav: float, current_portfolio: dict, market_signals: dict, forecast_results: list) -> dict:
    now_str = datetime.now(TAIPEI_TZ).isoformat()
    
    # 1. Sources (資料來源，新增 content_as_of)
    sources = [{
        "source_id": "S1",
        "authority": "twse",
        "url": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        "content_as_of": f"{trade_date}T13:30:00+08:00"
    }]
    
    # 2. Market View (市場總覽，包含 regime / stance / posture)
    market_view = {
        "basis_refs": ["O1"],
        "logic": "市場整體訊號平穩，維持中性建倉策略。",
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
    orders = []
    
    for idx, res in enumerate(forecast_results, 1):
        s_id = res["stock_id"]
        inf_id = f"I{idx}"
        dec_id = f"D{idx}"
        
        inferences.append({
            "inf_id": inf_id,
            "premise_refs": ["O1"],
            "logic": res.get("logic", "依據 AI 量化模型評分做出判斷。"),
            "counter_evidence": None
        })
        
        decisions.append({
            "decision_id": dec_id,
            "ticker": s_id,
            "action": "BUY" if res["signal"] == "BUY" else "HOLD",
            "target_weight": 0.04,
            "inference_refs": [inf_id]
        })
        
        orders.append({
            "ticker": s_id,
            "side": "BUY" if res["signal"] == "BUY" else "SELL",
            "shares": 1000,
            "decision_ref": dec_id
        })

    return {
        "schema_version": "4.2",
        "doc_type": "D-Plan",
        "team_id": team_id,
        "trade_date": trade_date,
        "sources": sources,
        "observations": [{"obs_id": "O1", "source_ref": ["S1"], "statement": "台股主要標的每日價量與技術面指標更新", "values": {}}],
        "market_view": market_view,
        "inferences": inferences,
        "decisions": decisions,
        "no_trade_decisions": [],
        "orders": orders,
        "agent_metadata": {
            "model_provider": "anthropic",
            "model_version": "claude-3-5-sonnet",
            "run_started_at": now_str,
            "run_completed_at": now_str,
            "code_version": "git:main"
        }
    }
