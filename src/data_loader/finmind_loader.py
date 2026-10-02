import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from FinMind.data import DataLoader

class FinMindDataLoader:
    def __init__(self, api_token: str = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiYWFyb24wNyIsImVtYWlsIjoiaHVpaHVpMjU1NmhAZ21haWwuY29tIiwidG9rZW5fdmVyc2lvbiI6MX0.BdgiGJOgolh7XdygpW4IUe_6i35KLenzNPTufGRpHVY"):
        self.dl = DataLoader()
        if api_token:
            try:
                self.dl.login_by_token(api_token)
                print("FinMind Token 驗證登入成功！")
            except Exception as e:
                print(f"FinMind Token 登入失敗: {e}")

    def get_stock_price_yahoo(self, stock_id: str) -> pd.DataFrame:
        """從 Yahoo Finance (奇摩) 抓取穩定且精準的台股歷史 K 線價格"""
        # 台股上市加 .TW，上櫃加 .TWO
        ticker_symbol = f"{stock_id}.TW"
        try:
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period="1mo")
            if df.empty:
                # 若上市抓不到，嘗試上櫃代碼 .TWO
                ticker = yf.Ticker(f"{stock_id}.TWO")
                df = ticker.history(period="1mo")
            
            if not df.empty:
                df = df.reset_index()
                df.rename(columns={"Close": "close", "Volume": "volume", "High": "high", "Low": "low", "Open": "open"}, inplace=True)
            return df
        except Exception as e:
            print(f"Yahoo Finance 抓取 {stock_id} 失敗: {e}")
            return pd.DataFrame()

    def get_institutional_chips(self, stock_id: str) -> float:
        """從 FinMind 抓取近 5 日三大法人買賣超淨額 (籌碼面)"""
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        try:
            df = self.dl.taiwan_stock_institutional_investors(
                stock_id=stock_id,
                start_date=start_date
            )
            if df is not None and not df.empty and "buy" in df.columns and "sell" in df.columns:
                df["net_buy"] = df["buy"] - df["sell"]
                recent_net = df["net_buy"].tail(5).sum()
                return float(recent_net)
            return 0.0
        except Exception as e:
            print(f"FinMind 籌碼抓取 {stock_id} 異常: {e}")
            return 0.0
