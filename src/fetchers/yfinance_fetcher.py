import pandas as pd
import yfinance as yf
import time
import os
import sqlite3

# 🎯 載入您建立的官方標的字典
from src.stock_list.official_stocks import ESUN_OFFICIAL_150_STOCKS

def fetch_and_split_max_history_interactive():
    # ==========================================
    # 🎯 0. 建立專屬的資料儲存資料夾
    # ==========================================
    output_dir = "historical_data"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"\n📁 尚未有資料夾，已自動建立專屬資料夾：{output_dir}")
    else:
        print(f"\n📁 儲存資料夾 {output_dir} 已存在。")

    # 將暫存資料庫也放在該資料夾下
    temp_db = os.path.join(output_dir, "temp_stock_data.db")
    
    # ==========================================
    # 🎯 1. 互動式詢問：設定「要抓取的筆數」
    # ==========================================
    print("\n" + "="*50)
    limit_input = input("📊 請輸入要抓取的股票筆數 (輸入 'all' 代表抓全部，輸入數字代表抓前 N 筆): ").strip()
    print("="*50 + "\n")

    # ==========================================
    # 🎯 2. 直接讀取官方名單
    # ==========================================
    print("正在載入 AI CUP 官方 150 檔標的清單...")
    
    tickers = []
    ticker_to_name = {}
    
    for stock_id, stock_name in ESUN_OFFICIAL_150_STOCKS.items():
        # Yahoo Finance 預設以上市 (.TW) 嘗試
        yahoo_ticker = f"{stock_id}.TW"
        tickers.append(yahoo_ticker)
        ticker_to_name[yahoo_ticker] = stock_name

    # ==========================================
    # 🎯 3. 調整要抓取的筆數並開始抓取
    # ==========================================
    if limit_input.lower() != 'all' and limit_input.isdigit():
        limit = int(limit_input)
        tickers = tickers[:limit]
        print(f"⚠️ 測試模式：已設定僅抓取名單中的前 {limit} 檔股票。")
    else:
        print(f"🚀 全量模式：將抓取名單上所有 {len(tickers)} 檔股票。")

    # 連接暫存資料庫
    if os.path.exists(temp_db):
        os.remove(temp_db)
    conn = sqlite3.connect(temp_db)

    # 欄位定義
    columns_mapping = {
        'Ticker': 'Yahoo 代號', 'Name': '公司名稱', 'Date': '交易日期',
        'Open': '開盤價', 'High': '最高價', 'Low': '最低價', 'Close': '收盤價', 'Volume': '成交量'
    }
    keep_cols = ['Yahoo 代號', '公司名稱', '交易日期', '開盤價', '最高價', '最低價', '收盤價', '成交量']
    period = "max" 
    
    print(f"\n開始從 Yahoo Finance 抓取資料 (範圍: {period})...")
    print("💡 啟用【資料庫中繼技術】，記憶體將自動釋放！")

    # 4. 逐一抓取股票，存入資料庫
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] 正在抓取: {ticker} ({ticker_to_name.get(ticker)})...")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)

            # 若 .TW 抓不到資料，嘗試切換成 .TWO (上櫃)
            if df.empty and ticker.endswith('.TW'):
                two_ticker = ticker.replace('.TW', '.TWO')
                print(f"  > 🔄 {ticker} 無資料，嘗試切換為上櫃代號 {two_ticker}...")
                stock = yf.Ticker(two_ticker)
                df = stock.history(period=period)
                if not df.empty:
                    ticker = two_ticker
                    ticker_to_name[ticker] = ticker_to_name.pop(ticker.replace('.TWO', '.TW'))

            if not df.empty:
                df = df.reset_index()
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                    df['Date_Str'] = df['Date'].dt.strftime('%Y-%m-%d')
                    df['Year'] = df['Date'].dt.strftime('%Y')
                    df['YearMonth'] = df['Date'].dt.strftime('%Y-%m')
                    df['Date'] = df['Date_Str']
                    
                df['Ticker'] = ticker
                df['Name'] = ticker_to_name.get(ticker, "未知公司")
                
                df = df.rename(columns=columns_mapping)
                all_needed_cols = keep_cols + ['Year', 'YearMonth']
                df = df[[c for c in all_needed_cols if c in df.columns]]
                
                df.to_sql('stock_table', conn, if_exists='append', index=False)
                del df 
            else:
                print(f"  > ⚠️ 警告: {ticker} 與 .TWO 皆無資料回傳")

        except Exception as e:
            print(f"  > ❌ 抓取 {ticker} 時發生錯誤: {e}")
        
        time.sleep(0.5)
        if i % 50 == 0:
            print(f"\n☕ 已連續爬取 {i} 檔，深度暫停 10 秒鐘...")
            time.sleep(10)

    # 5. 按照【年份】分檔，再按【月份】建立工作表並存入專屬資料夾
    print("\n資料全部抓取完畢！準備按「年分檔、月分頁」匯出 Excel 檔案...")
    
    try:
        check_empty = pd.read_sql('SELECT COUNT(*) FROM stock_table', conn).iloc[0,0]
        
        if check_empty > 0:
            years_df = pd.read_sql('SELECT DISTINCT Year FROM stock_table ORDER BY Year DESC', conn)
            unique_years = years_df['Year'].dropna().tolist()
            
            for year in unique_years:
                # 💡 將 Excel 檔案路徑加上剛建立的 output_dir
                output_file = os.path.join(output_dir, f"股市資料_{year}.xlsx")
                print(f"\n📁 正在處理年份：{year}，準備寫入 {output_file}...")
                
                with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                    months_query = f"SELECT DISTINCT YearMonth FROM stock_table WHERE Year = '{year}' ORDER BY YearMonth DESC"
                    months_df = pd.read_sql(months_query, conn)
                    unique_months = months_df['YearMonth'].tolist()
                    
                    for month_str in unique_months:
                        data_query = f"""
                            SELECT [Yahoo 代號], [公司名稱], [交易日期], [開盤價], [最高價], [最低價], [收盤價], [成交量] 
                            FROM stock_table 
                            WHERE YearMonth = '{month_str}'
                            ORDER BY [交易日期] DESC, [Yahoo 代號] ASC
                        """
                        month_data_df = pd.read_sql(data_query, conn)
                        sheet_name = f"{month_str.split('-')[1]}月"
                        
                        month_data_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        print(f"  ✅ 寫入完成: {year} 年 {sheet_name} (共 {len(month_data_df)} 筆)")
                        del month_data_df
                        
                print(f"🎉 '{output_file}' 儲存成功！(記憶體已重置)")
        else:
             print("⚠️ 找不到任何資料，可能抓取過程中發生錯誤或股票無歷史紀錄。")
                
    except Exception as e:
        print(f"❌ 寫入 Excel 時發生錯誤：{e}")

    # 6. 關閉並清理暫存資料庫
    conn.close()
    if os.path.exists(temp_db):
        os.remove(temp_db)
        print("\n🗑️ 暫存資料庫已自動清理完畢。")

    print("\n" + "="*50)
    print(f"🎉 大功告成！所有歷史資料已完美分類，並統一儲存於【{output_dir}】資料夾中！")
    print("="*50)

if __name__ == "__main__":
    fetch_and_split_max_history_interactive()
