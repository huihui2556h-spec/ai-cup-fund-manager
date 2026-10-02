import pandas as pd
from datetime import datetime, timedelta
from FinMind.data import DataLoader

class FinMindDataLoader:
    def __init__(self, api_token: str = ""):
        self.dl = DataLoader()
        if api_token:
            try:
                self.dl.login_by_token(api_token)
                print("FinMind Token 驗證成功！")
            except Exception as e:
                print(f"FinMind Token 登入失敗: {e}")

    def get_institutional_chips(self, stock_id: str) -> dict:
        """【fininst】三大法人籌碼資料"""
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        try:
            df = self.dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date)
            if df is not None and not df.empty and "buy" in df.columns and "sell" in df.columns:
                df["net_buy"] = df["buy"] - df["sell"]
                recent_net = float(df["net_buy"].tail(5).sum())
            else:
                recent_net = 0.0
        except Exception:
            recent_net = 0.0
            
        return {
            "authority": "fininst",
            "institutional_net_buy": recent_net
        }

    def get_month_revenue(self, stock_id: str) -> dict:
        """【mops】公開資訊觀測站 - 月營收 YoY"""
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        try:
            df = self.dl.taiwan_stock_month_revenue(stock_id=stock_id, start_date=start_date)
            if df is not None and not df.empty and "revenue_year_growth" in df.columns:
                latest_yoy = float(df["revenue_year_growth"].iloc[-1])
            else:
                latest_yoy = 0.0
        except Exception:
            latest_yoy = 0.0

        return {
            "authority": "mops",
            "revenue_yoy": latest_yoy
        }
