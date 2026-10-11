import os
import glob
import numpy as np
import pandas as pd

class MultiAuthorityForecastModel:
    def __init__(self):
        # 設定各 Authority 維度權重
        self.weights = {
            "twse_tpex": 0.35,  # 提高價量面與波動慣性權重 (因為我們有最精準的 CSV)
            "mops": 0.20,       # 基本面
            "fininst": 0.25,    # 籌碼面 (Institutional chips)
            "vendor": 0.10,     # 進階技術指標
            "media": 0.10       # 消息面
        }

    def predict_stock_score(self, stock_id: str, authority_data: dict) -> dict:
        sub_scores = {}
        
        # 1. twse / tpex (個股價量與波動慣性)
        twse_info = authority_data.get("twse_tpex", {})
        close = twse_info.get("close", 100)
        ma5 = twse_info.get("ma5", 100)
        ma20 = twse_info.get("ma20", 100)
        vol_ratio = twse_info.get("volume_ratio", 1.0)
        volatility_inertia = twse_info.get("volatility_inertia", 0.02)
        
        twse_score = 0.4
        if close >= ma5:
            twse_score += 0.2
        if close > ma5 > ma20: # 均線多頭排列
            twse_score += 0.2
        if vol_ratio > 1.2:    # 成交量放大
            twse_score += 0.1
        if volatility_inertia > 0.02: # 波動放大
            twse_score += 0.1
        sub_scores["twse_tpex"] = min(1.0, twse_score)

        # 2. mops (基本面營收)
        yoy = authority_data.get("mops", {}).get("revenue_yoy", 0)
        if yoy > 20: mops_score = 1.0
        elif yoy > 0: mops_score = 0.75
        elif yoy > -10: mops_score = 0.4
        else: mops_score = 0.1
        sub_scores["mops"] = mops_score

        # 3. fininst (法人籌碼面)
        net_buy = authority_data.get("fininst", {}).get("institutional_net_buy", 0)
        z_score = authority_data.get("fininst", {}).get("z_score", 0.0)
        if z_score > 1.0 or net_buy > 3000: fin_score = 1.0
        elif z_score > 0 or net_buy > 0: fin_score = 0.7
        elif z_score > -2000: fin_score = 0.35
        else: fin_score = 0.1
        sub_scores["fininst"] = fin_score

        # 4. vendor (進階技術面)
        rsi = authority_data.get("vendor", {}).get("rsi", 50)
        macd = authority_data.get("vendor", {}).get("macd_hist", 0)
        vendor_score = 0.5
        if 40 <= rsi <= 75: vendor_score += 0.25
        if macd > 0: vendor_score += 0.25
        sub_scores["vendor"] = vendor_score

        # 5. media (消息面情緒)
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
    從本地 CSV 獲取精準價量資料，並搭配籌碼面計算 AI 動態分數
    """
    # 預設基準資料
    authority_data = {
        "twse_tpex": {"close": 100.0, "ma5": 100.0, "ma20": 100.0, "volume_ratio": 1.0, "volatility_inertia": 0.02},
        "mops": {"revenue_yoy": 5.0},
        "fininst": {"institutional_net_buy": 500, "z_score": 0.2},
        "vendor": {"rsi": 55, "macd_hist": 0.1},
        "media": {"sentiment_score": 0.6},
        "taifex": {"pc_ratio": 100.0}
    }

    # ==========================================
    # 🎯 核心升級：自動尋找並讀取最新的 CSV 歷史資料
    # ==========================================
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "..", "fetchers", "historical_data")
    
    try:
        csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
        if csv_files:
            csv_files.sort(reverse=True)
            latest_file = csv_files[0]
            
            df = pd.read_csv(latest_file, encoding='utf-8-sig')
            
            # 找出目標股票資料 (支援上市 .TW 與上櫃 .TWO)
            df_stock = df[df['Yahoo 代號'] == f"{stock_id}.TW"].copy()
            if df_stock.empty:
                df_stock = df[df['Yahoo 代號'] == f"{stock_id}.TWO"].copy()

            if not df_stock.empty and len(df_stock) >= 20:
                # 依日期由舊到新排序，才能正確計算移動平均線
                df_stock = df_stock.sort_values(by="交易日期", ascending=True)
                
                closes = df_stock['收盤價'].astype(float)
                volumes = df_stock['成交量'].astype(float)
                
                # 計算真實技術指標
                close_p = closes.iloc[-1]
                ma5_p = closes.rolling(window=5).mean().iloc[-1]
                ma20_p = closes.rolling(window=20).mean().iloc[-1]
                
                # 算成交量變化 (當日成交量 / 5日均量)
                vol_5ma = volumes.rolling(window=5).mean().iloc[-1]
                vol_ratio = volumes.iloc[-1] / vol_5ma if vol_5ma > 0 else 1.0
                
                # 算波動慣性 (5日報酬率標準差)
                returns = closes.pct_change()
                volatility_inertia = returns.rolling(window=5).std().iloc[-1]
                if pd.isna(volatility_inertia):
                    volatility_inertia = 0.02
                    
                # 將算出的真實數據注入 AI 的腦袋中
                authority_data["twse_tpex"] = {
                    "close": close_p,
                    "ma5": ma5_p,
                    "ma20": ma20_p,
                    "volume_ratio": vol_ratio,
                    "volatility_inertia": volatility_inertia
                }
    except Exception as e:
        print(f"⚠️ 從 CSV 讀取 {stock_id} 時發生錯誤: {e}")

    # ==========================================
    # 法人籌碼 (保留原本 FinMind 輔助抓取邏輯)
    # ==========================================
    if loader is not None:
        try:
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
        except Exception:
            pass # 如果 API 失敗，就不影響 CSV 算出來的技術面分數

    model = MultiAuthorityForecastModel()
    return model.predict_stock_score(stock_id, authority_data)
