import os
import sys
import importlib.util
import pandas as pd
import yfinance as yf
import time
import sqlite3

# ==========================================
# 🎯 0. 讀取實體檔案，繞過模組載入機制
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
target_file = os.path.join(os.path.dirname(current_dir), "stock_list", "official_stocks.py")

print(f"🔍 系統正在尋找股票名單檔案：{target_file}")

if not os.path.exists(target_file):
    print("❌ 嚴重錯誤：找不到檔案！")
    sys.exit(1)

spec = importlib.util.spec_from_file_location("official_stocks", target_file)
official_stocks_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(official_stocks_module)

tickers = []
ticker_to_name = {}

if hasattr(official_stocks_module, "ESUN_OFFICIAL_150_STOCKS"):
    STOCK_DATA = official_stocks_module.ESUN_OFFICIAL_150_STOCKS
    for stock_id, name in STOCK_DATA.items():
        tickers.append(f"{stock_id}.TW")
        ticker_to_name[f"{stock_id}.TW"] = name
elif hasattr(official_stocks_module, "OFFICIAL_STOCKS"):
    STOCK_DATA = official_stocks_module.OFFICIAL_STOCKS
    for stock_id in STOCK_DATA:
        tickers.append(f"{stock_id}.TW")
        ticker_to_name[f"{stock_id}.TW"] = "未知公司"
else:
    print("❌ 嚴重錯誤：檔案找到了，但在 official_stocks.py 中找不到正確的變數名稱！")
    sys.exit(1)

def fetch_and_split_max_history_interactive():
    output_dir = os.path.join(current_dir, "historical_data")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"\n📁 已自動建立專屬資料夾：{output_dir}")

    temp_db = os.path.join(output_dir, "temp_stock_data.db")
    
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        print("\n[🤖 GitHub Actions 模式] 自動設定為全量抓取。")
        limit_input = 'all'
    else:
        limit_input = input("📊 請輸入要抓取的股票筆數 (輸入 'all' 代表抓全部): ").strip()

    print(f"✅ 成功載入 AI CUP 官方 {len(tickers)} 檔標的清單！")
    
    local_tickers = tickers.copy()
    if limit_input.lower() != 'all' and limit_input.isdigit():
        limit = int(limit_input)
        local_tickers = local_tickers[:limit]
        
    if os.path.exists(temp_db):
        os.remove(temp_db)
    conn = sqlite3.connect(temp_db)

    columns_mapping = {
        'Ticker': 'Yahoo 代號', 'Date': '交易日期',
        'Open': '開盤價', 'High': '最高價', 'Low': '最低價', 'Close': '收盤價', 'Volume': '成交量'
    }
    keep_cols = ['Yahoo 代號', '公司名稱', '交易日期', '開盤價', '最高價', '最低價', '收盤價', '成交量']
    period = "max" 
    
    print(f"\n開始從 Yahoo Finance 抓取資料 (範圍: {period})...")

    for i, ticker in enumerate(local_tickers, 1):
        print(f"[{i}/{len(local_tickers)}] 正在抓取: {ticker} ({ticker_to_name.get(ticker, '')})...")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)

            # 嘗試切換上櫃代號
            if df.empty and ticker.endswith('.TW'):
                two_ticker = ticker.replace('.TW', '.TWO')
                stock = yf.Ticker(two_ticker)
                df = stock.history(period=period)
                if not df.empty:
                    ticker_to_name[two_ticker] = ticker_to_name.pop(ticker)
                    ticker = two_ticker

            if not df.empty:
                df = df.reset_index()
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                    df['Date_Str'] = df['Date'].dt.strftime('%Y-%m-%d')
                    df['Year'] = df['Date'].dt.strftime('%Y')
                    df['Date'] = df['Date_Str']
                    
                df['Ticker'] = ticker
                df['Name'] = ticker_to_name.get(ticker, "未知公司")
                
                df = df.rename(columns=columns_mapping)
                all_needed_cols = keep_cols + ['Year']
                df = df[[c for c in all_needed_cols if c in df.columns]]
                
                df.to_sql('stock_table', conn, if_exists='append', index=False)
                del df 

        except Exception as e:
            print(f"  > ❌ 抓取 {ticker} 時發生錯誤: {e}")
        
        time.sleep(0.5)
        if i % 50 == 0:
            time.sleep(5)

    print("\n準備匯出 CSV 檔案 (以年份分檔)...")
    try:
        check_empty = pd.read_sql('SELECT COUNT(*) FROM stock_table', conn).iloc[0,0]
        if check_empty > 0:
            years_df = pd.read_sql('SELECT DISTINCT Year FROM stock_table ORDER BY Year DESC', conn)
            unique_years = years_df['Year'].dropna().tolist()
            
            for year in unique_years:
                output_file = os.path.join(output_dir, f"股市資料_{year}.csv")
                
                # 直接撈取該年度所有資料
                data_query = f"""
                    SELECT [Yahoo 代號], [公司名稱], [交易日期], [開盤價], [最高價], [最低價], [收盤價], [成交量] 
                    FROM stock_table 
                    WHERE Year = '{year}'
                    ORDER BY [交易日期] DESC, [Yahoo 代號] ASC
                """
                year_data_df = pd.read_sql(data_query, conn)
                
                # 輸出為 CSV，指定 utf-8-sig 以完美支援 Excel 開啟中文
                year_data_df.to_csv(output_file, index=False, encoding='utf-8-sig')
                print(f"🎉 '{output_file}' 儲存成功！(共 {len(year_data_df)} 筆)")
                del year_data_df
                
        else:
             print("⚠️ 找不到任何資料。")
    except Exception as e:
        print(f"❌ 寫入 CSV 時發生錯誤：{e}")

    conn.close()
    if os.path.exists(temp_db):
        os.remove(temp_db)

if __name__ == "__main__":
    fetch_and_split_max_history_interactive()
