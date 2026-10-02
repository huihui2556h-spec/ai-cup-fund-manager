import pandas as pd
from datetime import datetime, timedelta
from FinMind.data import DataLoader

class FinMindDataLoader:
    def __init__(self, api_token: str = ""):
        self.api_token = eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiYWFyb24wNyIsImVtYWlsIjoiaHVpaHVpMjU1NmhAZ21haWwuY29tIiwidG9rZW5fdmVyc2lvbiI6MX0.BdgiGJOgolh7XdygpW4IUe_6i35KLenzNPTufGRpHVY
        self.dl = DataLoader()
        if api_token:
            self.dl.login_by_token(api_token)

    def get_stock_price(self, stock_id: str, start_date: str = None) -> pd.DataFrame:
        """抓取個股近期的日 K 線歷史資料"""
        if not start_date:
            start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
            
        try:
            df = self.dl.taiwan_stock_daily(
                stock_id=stock_id,
                start_date=start_date
            )
            return df
        except Exception as e:
            print(f"Error fetching price for {stock_id}: {e}")
            return pd.DataFrame()
