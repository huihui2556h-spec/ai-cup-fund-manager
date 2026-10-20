import os
import json
from google import genai

def get_ai_portfolio_decisions(target_stocks_data, market_context):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    if not api_key:
        print("[系統提示] 未偵測到 GEMINI_API_KEY，啟用智慧籌碼排序。")
        return _fallback_decisions(target_stocks_data)

    try:
        # 如果是 AQ. 開頭的 GCP 憑證，直接透過環境變數傳遞，或透過 client 初始化
        os.environ["GEMINI_API_KEY"] = api_key
        
        # 初始化 Gemini Client
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
            "market_logic": "市場中性震盪，透過AI多維度籌碼與基本面篩選強勢標的",
            "decisions": [
                {{"ticker": "股票代碼4碼", "action": "BUY", "target_weight": 0.04, "reason": "AI 深度分析選股理由"}}
            ]
        }}
        """

        # 這裡改用 gemini-2.5-flash 或 gemini-2.5-pro 確保穩定回應
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
        print(f"[AI 大腦錯誤] 呼叫 Gemini 失敗: {e}")
        return _fallback_decisions(target_stocks_data)

def _fallback_decisions(target_stocks_data):
    sorted_fallback = sorted(target_stocks_data, key=lambda x: x.get("net_buy", 0), reverse=True)
    top_25 = sorted_fallback[:25]
    decisions = []
    for s in top_25:
        decisions.append({
            "ticker": s["stock_id"],
            "action": "BUY",
            "target_weight": round(0.90 / 25, 4),
            "reason": f"法人買超金額 {s.get('net_buy', 0):,.0f}，籌碼面強勢"
        })
    return {
        "market_regime": "neutral",
        "market_logic": "AI 離線智慧籌碼篩選（API 驗證降級保護）",
        "decisions": decisions
    }
