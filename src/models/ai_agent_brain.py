import os
import json
from google import genai

def get_ai_portfolio_decisions(target_stocks_data: list, market_context: dict) -> dict:
    """
    透過 Gemini SDK 進行智慧選股，並加入完整的錯誤防禦機制，
    當 API 金鑰驗證失敗或額度超過時，會自動切換為籌碼智慧排序，絕不當機。
    """
    # 支援環境變數或 Streamlit Secrets
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    # 若無金鑰或金鑰格式不符標準，直接啟動備用防禦機制
    if not api_key:
        print("[AI 提示] 未偵測到有效的 GEMINI_API_KEY，啟用籌碼智慧排序。")
        return _fallback_decisions(target_stocks_data, "未設定 API Key")

    try:
        # 強制設定環境變數供 Google GenAI SDK 讀取
        os.environ["GEMINI_API_KEY"] = api_key
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        你是一位專業的 AI 基金經理人，正在參與 2026 玉山 AI 挑戰賽。
        請根據以下的市場背景與候選股票的真實數據，挑選出 20 到 30 檔最佳投資標的，並分配目標權重。
        
        【競賽規則限制】
        1. 持股總檔數必須嚴格保持在 20 ~ 30 檔之間。
        2. 台積電 (2330) 權重上限為 25%。
        3. 其餘個股權重上限為 10%。
        4. 總股票配置資金佔比約 90%，現金保留 10% (< 25% 限制)。
        
        【市場背景資料】
        {json.dumps(market_context, ensure_ascii=False)}
        
        【候選股票真實數據摘要】
        {json.dumps(target_stocks_data[:60], ensure_ascii=False)}
        
        請以純 JSON 格式回傳你的決策結果，不要包含任何 markdown 標籤（如 ```json），格式如下：
        {{
            "market_regime": "neutral",
            "market_logic": "透過 AI 多維度籌碼與基本面篩選強勢標的",
            "decisions": [
                {{"ticker": "股票代碼4碼", "action": "BUY", "target_weight": 0.04, "reason": "AI 深度分析選股理由"}}
            ]
        }}
        """

        # 呼叫 Gemini Flash 模型
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        text_res = response.text.strip()
        if text_res.startswith("```json"):
            text_res = text_res[7:]
        if text_res.startswith("```"):
            text_res = text_res[3:]
        if text_res.endswith("```"):
            text_res = text_res[:-3]
            
        result_json = json.loads(text_res.strip())
        print("✅ 成功透過 Gemini AI 取得自主決策！")
        return result_json

    except Exception as e:
        print(f"[⚠️ AI 大腦攔截到 API 異常] {e}")
        # 當發生 ClientError 或授權失敗時，自動降級為智慧籌碼排序，確保賽事系統正常運作
        return _fallback_decisions(target_stocks_data, f"API 驗證或請求異常: {str(e)[:50]}")

def _fallback_decisions(target_stocks_data, reason_prefix):
    sorted_fallback = sorted(target_stocks_data, key=lambda x: x.get("net_buy", 0), reverse=True)
    top_25 = sorted_fallback[:25]
    decisions = []
    for s in top_25:
        decisions.append({
            "ticker": s["stock_id"],
            "action": "BUY",
            "target_weight": round(0.90 / 25, 4),
            "reason": f"法人籌碼強勢淨買超 (備用機制啟用)"
        })
    return {
        "market_regime": "neutral",
        "market_logic": f"系統自動保護降級 ({reason_prefix})",
        "decisions": decisions
    }
