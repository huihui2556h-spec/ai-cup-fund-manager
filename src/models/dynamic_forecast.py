import numpy as np

class MultiAuthorityForecastModel:
    def __init__(self):
        # 設定各 Authority 維度權重
        self.weights = {
            "twse_tpex": 0.25,  # 價量面
            "mops": 0.25,       # 基本面
            "fininst": 0.25,    # 籌碼面
            "vendor": 0.15,     # 進階技術指標
            "media": 0.10       # 消息面
        }

    def predict_stock_score(self, stock_id: str, authority_data: dict) -> dict:
        """
        authority_data 格式說明:
        {
            "twse_tpex": {"close": 150, "ma5": 148, "ma20": 142, "volume_ratio": 1.3},
            "mops": {"revenue_yoy": 15.2},
            "fininst": {"institutional_net_buy": 2500},
            "vendor": {"rsi": 62, "macd_hist": 1.5},
            "media": {"sentiment_score": 0.70},
            "taifex": {"pc_ratio": 108.0}
        }
        """
        sub_scores = {}

        # 1. twse / tpex (個股價量 25%)
        twse_info = authority_data.get("twse_tpex", {})
        close = twse_info.get("close", 0)
        ma5 = twse_info.get("ma5", 0)
        ma20 = twse_info.get("ma20", 0)
        vol_ratio = twse_info.get("volume_ratio", 1.0)
        
        twse_score = 0.5
        if close > ma5 > ma20: twse_score += 0.3
        if vol_ratio > 1.2: twse_score += 0.2
        sub_scores["twse_tpex"] = min(1.0, twse_score)

        # 2. mops (基本面營收 25%)
        yoy = authority_data.get("mops", {}).get("revenue_yoy", 0)
        if yoy > 20: mops_score = 1.0
        elif yoy > 0: mops_score = 0.75
        elif yoy > -10: mops_score = 0.4
        else: mops_score = 0.1
        sub_scores["mops"] = mops_score

        # 3. fininst (法人籌碼 25%)
        net_buy = authority_data.get("fininst", {}).get("institutional_net_buy", 0)
        if net_buy > 3000: fin_score = 1.0
        elif net_buy > 0: fin_score = 0.7
        elif net_buy > -2000: fin_score = 0.35
        else: fin_score = 0.1
        sub_scores["fininst"] = fin_score

        # 4. vendor (進階技術面 15%)
        rsi = authority_data.get("vendor", {}).get("rsi", 50)
        macd = authority_data.get("vendor", {}).get("macd_hist", 0)
        vendor_score = 0.5
        if 50 <= rsi <= 75: vendor_score += 0.25
        if macd > 0: vendor_score += 0.25
        sub_scores["vendor"] = vendor_score

        # 5. media (消息面情緒 10%)
        sub_scores["media"] = authority_data.get("media", {}).get("sentiment_score", 0.5)

        # 計算基礎加權得分
        base_score = sum(sub_scores[k] * self.weights[k] for k in self.weights)

        # 6. taifex (期交所大盤調控乘數)
        pc_ratio = authority_data.get("taifex", {}).get("pc_ratio", 100.0)
        taifex_mult = 1.10 if pc_ratio >= 110 else (0.85 if pc_ratio < 90 else 1.0)

        final_score = round(min(1.0, base_score * taifex_mult), 3)

        return {
            "stock_id": stock_id,
            "forecast_score": final_score,
            "sub_scores": sub_scores,
            "market_multiplier": taifex_mult
        }

def ai_dynamic_forecast(stock_id: str, authority_data: dict):
    """供 app.py 舊介面呼叫的相容函式"""
    model = MultiAuthorityForecastModel()
    return model.predict_stock_score(stock_id, authority_data)
