import sys
import os

# ==========================================
# 🎯 0. 【終極修復】強制將專案根目錄加入系統路徑
# ==========================================
# 取得目前這個檔案的絕對路徑，並往上推兩層回到專案根目錄
current_dir = os.path.dirname(os.path.abspath(__file__)) # 目前在 src/fetchers
src_dir = os.path.dirname(current_dir)                   # 往上一層到 src
project_root = os.path.dirname(src_dir)                  # 再往上一層到根目錄

# 強制把根目錄塞進 Python 的搜尋路徑最前面
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
import yfinance as yf
import time
import sqlite3

# 現在絕對可以順利載入 src 裡面的東西了！
from src.stock_list.official_stocks import OFFICIAL_STOCKS

def fetch_and_split_max_history_interactive():
    # 建立儲存資料夾
    output_dir = os.path.join(current_dir, "historical_data")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"\n📁 已自動建立專屬資料夾：{output_dir}")

    temp_db = os.path.join(output_dir, "temp_stock_data.db")
    
    # 判斷是否為 GitHub Actions
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        print("\n[🤖 GitHub Actions 模式] 自動設定為全量抓取。")
        limit_input = 'all'
    else:
        limit_input = input("📊 請輸入要抓取的股票筆數 (輸入 'all' 代表抓全部): ").strip()

    print("正在載入 AI CUP 官方 150 檔標的清單...")
    tickers = []
    
    # 使用最初版本的 OFFICIAL_STOCKS 清單
    for stock_id in OFFICIAL_STOCKS:
        yahoo_ticker = f"{stock_id}.TW"
        tickers.append(yahoo_ticker)

    if limit_input.lower() != 'all' and limit_input.isdigit():
        limit = int(limit_input)
        tickers = tickers[:limit]
        
    if os.path.exists(temp_db):
        os.remove(temp_db)
    conn = sqlite3.connect(temp_db)

    columns_mapping = {
        'Ticker': 'Yahoo 代號', 'Date': '交易日期',
        'Open': '開盤價', 'High': '最高價', 'Low': '最低價', 'Close': '收盤價', 'Volume': '成交量'
    }
    keep_cols = ['Yahoo 代號', '交易日期', '開盤價', '最高價', '最低價', '收盤價', '成交量']
    period = "max" 
    
    print(f"\n開始從 Yahoo Finance 抓取資料 (範圍: {period})...")

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] 正在抓取: {ticker}...")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)

            if df.empty and ticker.endswith('.TW'):
                two_ticker = ticker.replace('.TW', '.TWO')
                stock = yf.Ticker(two_ticker)
                df = stock.history(period=period)
                if not df.empty:
                    ticker = two_ticker

            if not df.empty:
                df = df.reset_index()
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                    df['Date_Str'] = df['Date'].dt.strftime('%Y-%m-%d')
                    df['Year'] = df['Date'].dt.strftime('%Y')
                    df['YearMonth'] = df['Date'].dt.strftime('%Y-%m')
                    df['Date'] = df['Date_Str']
                    
                df['Ticker'] = ticker
                df = df.rename(columns=columns_mapping)
                all_needed_cols = keep_cols + ['Year', 'YearMonth']
                df = df[[c for c in all_needed_cols if c in df.columns]]
                
                df.to_sql('stock_table', conn, if_exists='append', index=False)
                del df 

        except Exception as e:
            print(f"  > ❌ 抓取 {ticker} 時發生錯誤: {e}")
        
        time.sleep(0.5)
        if i % 50 == 0:
            time.sleep(5)

    print("\n準備按「年分檔、月分頁」匯出 Excel 檔案...")
    try:
        check_empty = pd.read_sql('SELECT COUNT(*) FROM stock_table', conn).iloc[0,0]
        if check_empty > 0:
            years_df = pd.read_sql('SELECT DISTINCT Year FROM stock_table ORDER BY Year DESC', conn)
            unique_years = years_df['Year'].dropna().tolist()
            
            for year in unique_years:
                output_file = os.path.join(output_dir, f"股市資料_{year}.xlsx")
                with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                    months_query = f"SELECT DISTINCT YearMonth FROM stock_table WHERE Year = '{year}' ORDER BY YearMonth DESC"
                    months_df = pd.read_sql(months_query, conn)
                    unique_months = months_df['YearMonth'].tolist()
                    
                    for month_str in unique_months:
                        data_query = f"""
                            SELECT [Yahoo 代號], [交易日期], [開盤價], [最高價], [最低價], [收盤價], [成交量] 
                            FROM stock_table 
                            WHERE YearMonth = '{month_str}'
                            ORDER BY [交易日期] DESC, [Yahoo 代號] ASC
                        """
                        month_data_df = pd.read_sql(data_query, conn)
                        sheet_name = f"{month_str.split('-')[1]}月"
                        month_data_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        del month_data_df
                print(f"🎉 '{output_file}' 儲存成功！")
        else:
             print("⚠️ 找不到任何資料。")
    except Exception as e:
        print(f"❌ 寫入 Excel 時發生錯誤：{e}")

    conn.close()
    if os.path.exists(temp_db):
        os.remove(temp_db)

if __name__ == "__main__":
    fetch_and_split_max_history_interactive()
