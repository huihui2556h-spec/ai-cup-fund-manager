import pandas as pd
import numpy as np
from typing import Dict, Any
from src.data_loader.finmind_loader import FinMindDataLoader

def ai_dynamic_forecast(
    stock_id: str,
    df_price: pd.DataFrame = None,
    df_chips: pd.DataFrame = None,
    loader: FinMindDataLoader = None
) -> Dict[str, Any]:
    """
    AI 動態分析與預測模組
    從網路抓取的實時資料中提取特徵，並透過統計與動態模型進行預測
    """
    if loader is None:
        loader = FinMindDataLoader()

    # 1. 確保取得最新資料
    if df_price is None or df_price.empty:
        df_price = loader.get_stock_price(stock_id)
    if df_chips is None or df_chips.empty:
        df_chips = loader.get_institutional_chips(stock_id)

    if df_price.empty or "close" not in df_price.columns:
        return {
            "stock_id": stock_id,
            "forecast_score": 0.5,
            "signal": "HOLD",
            "reason": "無法從網路取得有效價格數據"
        }

    # 2. 特徵計算：價格動量 (Momentum)
    closes = df_price["close"].values
    if len(closes) >= 5:
        returns = np.diff(closes) / closes[:-1]
        recent_momentum = np.mean(returns[-5:])
    else:
        recent_momentum = 0.0

    # 3. 特徵計算：三大法人籌碼 Z-Score 與機率映射
    if not df_chips.empty and len(df_chips) >= 3:
        total_net = df_chips["foreign_investors"] + df_chips["investment_trust"]
        mean_net = total_net.mean()
        std_net = total_net.std()
        
        if std_net > 0:
            latest_net = total_net.iloc[-1]
            chip_z_score = (latest_net - mean_net) / std_net
            chip_probability = 1 / (1 + np.exp(-chip_z_score))
        else:
            chip_z_score = 0.0
            chip_probability = 0.5
    else:
        chip_z_score = 0.0
        chip_probability = 0.5

    # 4. 波動度慣性計算
    volatility = loader.calculate_volatility_inertia(df_price)
    
    # 5. 綜合 AI 動態預測評分
    momentum_score = 1 / (1 + np.exp(-recent_momentum * 20))
    final_score = (chip_probability * 0.55) + (momentum_score * 0.45)
    
    if volatility > 0.4:
        final_score = final_score * 0.9

    final_score = float(round(np.clip(final_score, 0.0, 1.0), 4))

    if final_score >= 0.62:
        signal = "BUY"
    elif final_score <= 0.38:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "stock_id": stock_id,
        "forecast_score": final_score,
        "signal": signal,
        "analysis_details": {
            "momentum_score": round(momentum_score, 4),
            "chip_probability": round(chip_probability, 4),
            "chip_z_score": round(chip_z_score, 4),
            "annual_volatility": round(volatility, 4)
        }
    }


if __name__ == "__main__":
    loader_inst = FinMindDataLoader()
    result = ai_dynamic_forecast("2330", loader=loader_inst)
    print(result)
