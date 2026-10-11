import os
import json
from google import genai
from google.genai import types

def fetch_dynamic_ai_analysis(forecast_results, nav):
    """
    動態呼叫 Gemini API 根據當前股票預測與籌碼數據生成專業基金經理人觀點
    """
    # 整理傳給 AI 的數據摘要
    summary_data = []
    for res in forecast_results:
        summary_data.append({
            "stock_id": res["stock_id"],
            "score": res["forecast_score"],
            "signal": res["signal"],
            "details": res.get("analysis_details", {})
        })
    
    prompt = f"""
    你是一位頂尖的投信基金經理人，目前管理 10 億元台股 ETF 虛擬基金。
    請根據以下各檔股票的 AI 預測分數、籌碼 Z-Score 與動量指標：
    {summary_data}
    
    請以專業、合規的口吻進行動態分析，並嚴格以 JSON 格式回傳以下兩個欄位：
    1. "market_logic": 一段專業的整體市場觀點邏輯（對應 D-Plan 的 market_view 描述，分析大盤與資金動向）。
    2. "stock_inferences": 一個字典（dict），鍵為股票代碼（stock_id），值為該檔股票的專業推論邏輯文字（對應 D-Plan 的 inferences）。
    """

    try:
        # 動態抓取環境變數中的 GEMINI_API_KEY
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("⚠️ 警告：未偵測到 GEMINI_API_KEY 環境變數，將改用動態量化生成邏輯。")
            return None

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ AI API 呼叫失敗: {e}，將自動切換為動態備用邏輯。")
        return None
