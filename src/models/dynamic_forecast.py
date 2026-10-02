import pandas as pd
import numpy as np

def ai_dynamic_forecast(stock_id: str, loader) -> dict:
    """綜合 奇摩技術面 + FinMind 籌碼面 之 AI 多因子推理模型"""
    
    # 1. 奇摩價格源 (Yahoo Finance)
    df_p = loader.get_stock_price_yahoo(stock_id)
    
    close_price = 100.0
    tech_score = 0.50
    chip_score = 0.50
    
    if df_p is not None and not df_p.empty and "close" in df_p.columns:
        close_price = float(df_p["close"].iloc[-1])
        
        # 技術面因子計算 (5日線與20日線趨勢)
        if len(df_p) >= 5:
            ma5 = df_p["close"].tail(5).mean()
            ma20 = df_p["close"].mean() if len(df_p) >= 20 else ma5
            
            # 技術動能得分
            bias = (close_price - ma5) / ma5 if ma5 > 0 else 0
            trend = (ma5 - ma20) / ma20 if ma20 > 0 else 0
            tech_score = float(np.clip(0.50 + (bias * 3) + (trend * 2), 0.10, 0.90))

    # 2. FinMind 籌碼源 (三大法人籌碼)
    chip_net = loader.get_institutional_chips(stock_id)
    if chip_net > 5000:       # 法人強勢大買
        chip_score = 0.85
    elif chip_net > 0:        # 法人小買
        chip_score = 0.65
    elif chip_net < -5000:    # 法人強勢大賣
        chip_score = 0.15
    else:                     # 法人觀望
        chip_score = 0.45

    # 3. AI 綜合加權評分 (技術面 50% + 籌碼面 50%)
    final_score = float(np.clip(0.50 * tech_score + 0.50 * chip_score, 0.05, 0.95))
    
    # 判定訊號
    if final_score >= 0.65:
        signal = "BUY"
    elif final_score <= 0.35:
        signal = "SELL"
    else:
        signal = "HOLD"

    # 4. 生成「有理有據」推理邏輯鏈 (Schema 4.2 專用)
    chip_desc = "三大法人近期顯著買超加碼" if chip_score > 0.6 else ("三大法人籌碼調節流出" if chip_score < 0.4 else "三大法人動向中性")
    tech_desc = "價格突破短均線展現強勢動能" if tech_score > 0.6 else "技術面陷入震盪盤整"
    
    logic_str = f"標的 {stock_id} 當前價 ${close_price:.2f}。AI 評分 {final_score:.2f}（技術面評分: {tech_score:.2f}，籌碼面評分: {chip_score:.2f}）。分析顯示：{tech_desc}，且{chip_desc}，綜合決策執行 {signal} 策略。"

    return {
        "stock_id": stock_id,
        "forecast_score": round(final_score, 4),
        "signal": signal,
        "close_price": close_price,
        "chip_net": chip_net,
        "logic": logic_str
    }
