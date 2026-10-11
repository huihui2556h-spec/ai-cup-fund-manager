import os
import json
from google import genai
from google.genai import types
from src.stock_list.official_stocks import get_official_stock_name

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def fetch_dynamic_ai_analysis(forecast_results, nav):
    """
    使用競賽 150 檔官方名單進行 AI 分析與推論生成
    """
    summary_data = []
    for res in forecast_results:
        stock_id = str(res["stock_id"])
        stock_name = get_official_stock_name(stock_id)
        summary_data.append({
            "stock_id": stock_id,
            "stock_name": stock_name,
            "score": res["forecast_score"],
            "signal": res["signal"],
            "details": res.get("analysis_details", {})
        })
    
    prompt = f"""
    你是一位頂尖的投信基金經理人，目前管理 10 億元台股 ETF 虛擬基金。
    請根據以下各檔股票（皆為 AI CUP 2026 競賽指定標的）的預測分數、籌碼 Z-Score 與動量指標：
    {summary_data}
    
    請以專業、合規的台股投信口吻進行動態分析，並嚴格以 JSON 格式回傳以下兩個欄位：
    1. "market_logic": 一段專業的整體市場觀點邏輯（對應 D-Plan 的 market_view 描述）。
    2. "stock_inferences": 一個字典（dict），鍵為股票代碼（stock_id），值為該檔股票包含公司名稱與量化數據的專業推論邏輯文字（對應 D-Plan 的 inferences）。
    """

    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
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
        print(f"❌ AI API 呼叫失敗: {e}")
        return None
