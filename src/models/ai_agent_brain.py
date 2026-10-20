import os
import json
from dotenv import load_dotenv
from google import genai

# 自動讀取 .env 檔案中的環境變數
load_dotenv()

def get_ai_portfolio_decisions(target_stocks_data: list, market_context: dict) -> dict:
    # 從環境變數獲取 API 金鑰
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("[錯誤] 未在 .env 檔案中找到 GEMINI_API_KEY！")
        return {}

    # 初始化 Google GenAI SDK 客戶端
    client = genai.Client(api_key=api_key)

    prompt = f"""
    你是一位 AI 基金經理人，正參與 2026 AI CUP 競賽。
    請分析以下市場數據並篩選 20-30 檔合規持股：
    {json.dumps(target_stocks_data[:50], ensure_ascii=False)}
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    return json.loads(response.text.strip())
