import os
from google import genai
from google.genai import types

def get_ai_market_and_stock_analysis(forecast_results, nav):
    """
    呼叫 Gemini AI 根據當前籌碼與數據生成專業的市場觀點與個股推論
    """
    # 整理給 AI 的數據摘要
    summary_data = []
    for res in forecast_results:
        summary_data.append({
            "stock_id": res["stock_id"],
            "score": res["forecast_score"],
            "signal": res["signal"],
            "details": res.get("analysis_details", {})
        })
    
    prompt = f"""
    你是一位頂尖的投信基金經理人與量化交易專家。目前管理 10 億元台股 ETF 虛擬基金。
    請根據以下各檔股票的 AI 預測分數、籌碼 Z-Score 與動量指標結果：
    {summary_data}
    
    請以專業、合規的口吻提供以下內容（請用 JSON 格式回傳，包含兩個欄位）：
    1. "market_logic": 一段專業的整體市場觀點邏輯（對應 D-Plan 的 market_view）。
    2. "stock_inferences": 一個字典，鍵為 stock_id，值為該檔股票的專業推論邏輯（對應 D-Plan 的 inferences）。
    """

    try:
        # 初始化 Gemini Client (需在環境變數設定 GEMINI_API_KEY)
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        import json
        return json.loads(response.text)
    except Exception as e:
        # 若 API Key 尚未設定或呼叫失敗時的備用邏輯
        print(f"AI API 呼叫提示: {e}，將使用預設量化邏輯生成。")
        return None
