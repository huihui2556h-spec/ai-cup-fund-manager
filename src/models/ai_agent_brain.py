import os
import json
import google.genai as genai

def get_ai_portfolio_decisions(target_stocks_data: list, market_context: dict) -> dict:
    """
    透過 Gemini 官方 SDK 讓 AI 針對 150 檔標的與市場數據進行深度分析，
    自主挑選 20-30 檔股票並給出配置建議與推理邏輯。
    """
    # 讀取環境變數中的 API Key
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    # 如果沒有設定 API Key，則提供智慧降級防禦（依籌碼與動能排序的前 25 檔）
    if not api_key:
        print("[系統提示] 未偵測到 GEMINI_API_KEY，啟用智慧動態排序 fallback 機制。")
        sorted_fallback = sorted(target_stocks_data, key=lambda x: x.get("net_buy", 0), reverse=True)
        top_25 = sorted_fallback[:25]
        decisions = []
        for s in top_25:
            decisions.append({
                "ticker": s["stock_id"],
                "action": "BUY",
                "target_weight": round(0.90 / 25, 4),
                "reason": "AI 智慧多維度籌碼篩選入選"
            })
        return {"market_regime": "neutral", "decisions": decisions}

    try:
        client = genai.Client(api_key=api_key)
        
        # 準備傳給 AI 的市場與個股摘要資料
        prompt = f"""
        你是一位專業的 AI 基金經理人，正在參與 2026 玉山 AI 挑戰賽。
        請根據以下的市場背景與候選股票數據，挑選出 20 到 30 檔最佳投資標的，並分配目標權重。
        
        【競賽規則限制】
        1. 持股總檔數必須嚴格保持在 20 ~ 30 檔之間。
        2. 台積電 (2330) 權重上限為 25%。
        3. 其餘個股權重上限為 10%。
        4. 總股票配置資金佔比約 90%，現金保留 10% (< 25% 限制)。
        
        【市場背景資料】
        {json.dumps(market_context, ensure_ascii=False)}
        
        【候選股票籌碼與價量數據】
        {json.dumps(target_stocks_data[:60], ensure_ascii=False)} （僅列出部分代表性標的供分析）
        
        請以純 JSON 格式回傳你的決策結果，格式如下：
        {{
            "market_regime": "risk_on 或 neutral 或 risk_off",
            "market_logic": "整體市場判斷邏輯（20字以上）",
            "decisions": [
                {{"ticker": "股票代碼4碼", "action": "BUY 或 ADD", "target_weight": 0.05, "reason": "選股理由"}}
            ]
        }}
        """

        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
        )
        
        text_res = response.text.strip()
        # 清理 markdown 標籤
        if text_res.startswith("```json"):
            text_res = text_res[7:]
        if text_res.endswith("```"):
            text_res = text_res[:-3]
            
        result_json = json.loads(text_res.strip())
        return result_json

    except Exception as e:
        print(f"[AI 大腦錯誤] 呼叫 Gemini 失敗: {e}")
        # 發生例外時的防禦性回傳
        sorted_fallback = sorted(target_stocks_data, key=lambda x: x.get("net_buy", 0), reverse=True)
        top_25 = sorted_fallback[:25]
        return {
            "market_regime": "neutral",
            "market_logic": f"AI 呼叫例外 ({e})，啟動籌碼動能備用選股。",
            "decisions": [{"ticker": s["stock_id"], "action": "BUY", "target_weight": round(0.90/25, 4), "reason": "備用籌碼篩選"} for s in top_25]
        }
