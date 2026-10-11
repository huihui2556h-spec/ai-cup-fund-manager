import numpy as np
import pandas as pd

class MultiAuthorityForecastModel:
    def __init__(self):
        # 設定各 Authority 維度權重
        self.weights = {
            "twse_tpex": 0.25,  # 價量面與波動慣性
            "mops": 0.25,       # 基本面
            "fininst": 0.25,    # 籌碼面 (Institutional chips)
            "vendor": 0.15,     # 進階技術指標
            "media": 0.10       # 消息面
        }

    def predict_stock_score(self, stock_id: str, authority_data: dict) -> dict:
        sub_scores = {}

        # 1. twse / tpex (個股價量與波動慣性 25%)
        twse_info = authority_data.get("twse_tpex", {})
        close = twse_info.get("close", 100)
        ma5 = twse_info.get("ma5", 100)
        ma20 = twse_info.get("ma20", 100)
        vol_ratio = twse_info.get("volume_ratio", 1.0)
        volatility_inertia = twse_info.get("volatility_inertia", 0.02)
        
        twse_score = 0.5
        if close >= ma5: twse_score += 0.2
        if close > ma5 > ma20: twse_score += 0.1
        if vol_ratio > 1.1: twse_score += 0.1
        if volatility_inertia > 0.01: twse_score += 0.1 # 納入波動慣性加分
        sub_scores["twse_tpex"] = min(1.0, twse_score)

        # 2. mops (基本面營收 25%)
        yoy = authority_data.get("mops", {}).get("revenue_yoy", 0)
        if yoy > 20: mops_score = 1.0
        elif yoy > 0: mops_score = 0.75
        elif yoy > -10: mops_score = 0.4
        else: mops_score = 0.1
        sub_scores["mops"] = mops_score

        # 3. fininst (法人籌碼面 25%)
        net_buy = authority_data.get("fininst", {}).get("institutional_net_buy", 0)
        z_score = authority_data.get("fininst", {}).get("z_score", 0.0)
        
        if z_score > 1.0 or net_buy > 3000: fin_score = 1.0
        elif z_score > 0 or net_buy > 0: fin_score = 0.7
        elif z_score > -2000: fin_score = 0.35
        else: fin_score = 0.1
        sub_scores["fininst"] = fin_score

        # 4. vendor (進階技術面 15%)
        rsi = authority_data.get("vendor", {}).get("rsi", 50)
        macd = authority_data.get("vendor", {}).get("macd_hist", 0)
        vendor_score = 0.5
        if 40 <= rsi <= 75: vendor_score += 0.25
        if macd > 0: vendor_score += 0.25
        sub_scores["vendor"] = vendor_score

        # 5. media (消息面情緒 10%)
        sub_scores["media"] = authority_data.get("media", {}).get("sentiment_score", 0.5)

        # 計算基礎加權得分
        base_score = sum(sub_scores[k] * self.weights[k] for k in self.weights)

        # 6. taifex (期交所大盤調控乘數)
        pc_ratio = authority_data.get("taifex", {}).get("pc_ratio", 100.0)
        taifex_mult = 1.10 if pc_ratio >= 110 else (0.85 if pc_ratio < 90 else 1.0)

        final_score = round(min(1.0, max(0.0, base_score * taifex_mult)), 3)

        return {
            "stock_id": stock_id,
            "forecast_score": final_score,
            "signal": "BUY" if final_score >= 0.45 else "HOLD",
            "sub_scores": sub_scores,
            "market_multiplier": taifex_mult
        }

def ai_dynamic_forecast(stock_id: str, loader=None):
    """
    支援自動向 FinMind 與市場資料源蒐集真實數據、計算波動慣性與籌碼的動態預測函式
    """
    # 預設基準資料（防止 API 失敗時完全崩潰）
    authority_data = {
        "twse_tpex": {"close": 100.0, "ma5": 100.0, "ma20": 100.0, "volume_ratio": 1.0, "volatility_inertia": 0.02},
        "mops": {"revenue_yoy": 5.0},
        "fininst": {"institutional_net_buy": 500, "z_score": 0.2},
        "vendor": {"rsi": 55, "macd_hist": 0.1},
        "media": {"sentiment_score": 0.6},
        "taifex": {"pc_ratio": 100.0}
    }

    # 如果有傳入 FinMind loader，則自動從後端撈取真實歷史數據
    if loader is not None:
        try:
            # 1. 抓取股價資料計算價量、移動平均與波動率慣性
            df_price = loader.get_stock_price(stock_id)
            if df_price is not None and not df_price.empty and "close" in df_price.columns:
                closes = df_price["close"].astype(float)
                close_p = float(closes.iloc[-1])
                ma5_p = float(closes.rolling(window=5).mean().iloc[-1]) if len(closes) >= 5 else close_p
                ma20_p = float(closes.rolling(window=20).mean().iloc[-1]) if len(closes) >= 20 else close_p
                
                # 計算波動慣性 (Volatility Inertia: 5日報酬率標準差)
                returns = closes.pct_change()
                volatility_inertia = float(returns.rolling(window=5).std().iloc[-1])
                if np.isnan(volatility_inertia): 
                    volatility_inertia = 0.02

                authority_data["twse_tpex"] = {
                    "close": close_p,
                    "ma5": ma5_p,
                    "ma20": ma20_p,
                    "volume_ratio": 1.2, # 若有成交量資料可在此替換
                    "volatility_inertia": volatility_inertia
                }

            # 2. 抓取法人籌碼資料計算 Institutional Chips & Z-Score
            if hasattr(loader, "get_institutional_investors"):
                df_chip = loader.get_institutional_investors(stock_id)
                if df_chip is not None and not df_chip.empty and "net_buy" in df_chip.columns:
                    net_buys = df_chip["net_buy"].astype(float)
                    net_buy_sum = float(net_buys.tail(3).sum())
                    z_score = float((net_buy_sum - net_buys.mean()) / (net_buys.std() + 1e-5))
                    authority_data["fininst"] = {
                        "institutional_net_buy": net_buy_sum,
                        "z_score": z_score
                    }
        except Exception as e:
            print(f"⚠️ 股票 {stock_id} 自動抓取 FinMind 資料發生例外，採用預設基準: {e}")

    model = MultiAuthorityForecastModel()
    return model.predict_stock_score(stock_id, authority_data)
