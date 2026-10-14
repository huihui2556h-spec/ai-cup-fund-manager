import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def get_finmind_data(loader, dataset, stock_id, start_date):
    """
    統一的資料抓取接口。
    請確認你的 FinMindDataLoader 中抓取資料的方法名稱。
    如果你的 loader 使用不同方法名稱(例如 loader.fetch() 或 loader.request())，請在此處修改。
    """
    try:
        # 假設 loader 具有通用的 get_data 方法
        # 如果你的 loader 沒有 get_data，可以嘗試直接用 loader.request(dataset=dataset, data_id=stock_id, start_date=start_date)
        if hasattr(loader, "get_data"):
            df = loader.get_data(dataset=dataset, data_id=stock_id, start_date=start_date)
        elif hasattr(loader, "request"):
            df = loader.request(dataset=dataset, data_id=stock_id, start_date=start_date)
        else:
            # 備用方案：若無法辨識 loader，回傳空表
            return pd.DataFrame()
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
    except Exception as e:
        print(f"抓取 {dataset} 發生錯誤: {e}")
        return pd.DataFrame()

def ai_dynamic_forecast(stock_id, loader=None):
    # 預設中立分數 (0.5)
    scores = {
        "twse_tpex": 0.5,
        "mops": 0.5,
        "fininst": 0.5,
        "vendor": 0.5,
        "media": 0.5
    }
    
    # 設定日期範圍 (抓取近 60 天數據)
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=60)).strftime('%Y-%m-%d')
    mops_start_date = (end_date - timedelta(days=365)).strftime('%Y-%m-%d') # 基本面看長一點
    
    if loader:
        try:
            # ==========================================
            # 1. 子指標_twse_tpex：技術面 (TaiwanStockPrice)
            # ==========================================
            df_price = get_finmind_data(loader, "TaiwanStockPrice", stock_id, start_date)
            if not df_price.empty and len(df_price) >= 20:
                df_price['MA5'] = df_price['close'].rolling(5).mean()
                df_price['MA20'] = df_price['close'].rolling(20).mean()
                latest = df_price.iloc[-1]
                
                # 給分邏輯：收盤價站上月線且五日線上穿二十日線，動能強給高分
                if latest['close'] > latest['MA20']:
                    scores['twse_tpex'] += 0.2
                if latest['MA5'] > latest['MA20']:
                    scores['twse_tpex'] += 0.15
                if latest['close'] < latest['MA20']:
                    scores['twse_tpex'] -= 0.2

            # ==========================================
            # 2. 子指標_mops：基本面 (TaiwanStockMonthRevenue)
            # ==========================================
            df_rev = get_finmind_data(loader, "TaiwanStockMonthRevenue", stock_id, mops_start_date)
            if not df_rev.empty and len(df_rev) >= 2:
                latest_rev = df_rev.iloc[-1]
                prev_rev = df_rev.iloc[-2]
                
                # 給分邏輯：月營收是否呈現月增 (MoM) 或年增 (YoY)
                if 'revenue_YoY' in df_rev.columns and latest_rev['revenue_YoY'] > 0:
                    scores['mops'] += 0.3
                elif latest_rev['revenue'] > prev_rev['revenue']: 
                    scores['mops'] += 0.2

            # ==========================================
            # 3. 子指標_fininst：籌碼面 (TaiwanStockInstitutionalInvestorsBuySell)
            # ==========================================
            df_inst = get_finmind_data(loader, "TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date)
            if not df_inst.empty:
                # 篩選近 5 天的三大法人合計買賣超
                df_inst_recent = df_inst.tail(15) 
                net_buy = df_inst_recent['buy'].sum() - df_inst_recent['sell'].sum()
                
                # 給分邏輯：法人整體呈現買超給高分，賣超扣分
                if net_buy > 0:
                    scores['fininst'] = 0.85
                elif net_buy < 0:
                    scores['fininst'] = 0.30

            # ==========================================
            # 4. 子指標_vendor：主力/散戶 (TaiwanStockMarginPurchaseShortSale)
            # 使用融資融券作為散戶或特定主力指標
            # ==========================================
            df_margin = get_finmind_data(loader, "TaiwanStockMarginPurchaseShortSale", stock_id, start_date)
            if not df_margin.empty:
                # 融資餘額變化
                recent_margin = df_margin.tail(5)['MarginPurchaseTodayBalance'].diff().sum()
                
                # 給分邏輯：融資減少(散戶退場，籌碼沉澱)給高分，融資大增扣分
                if recent_margin < 0:
                    scores['vendor'] = 0.75
                else:
                    scores['vendor'] = 0.40

            # ==========================================
            # 5. 子指標_media：新聞情緒面 (TaiwanStockNews)
            # ==========================================
            df_news = get_finmind_data(loader, "TaiwanStockNews", stock_id, start_date)
            if not df_news.empty and 'title' in df_news.columns:
                news_text = " ".join(df_news['title'].tolist())
                positive_keywords = ['成長', '利多', '創新高', '買超', '看好', '雙位數', '盈餘', '大增', '受惠']
                negative_keywords = ['衰退', '利空', '下跌', '賣超', '看壞', '探底', '虧損', '大減', '下修']
                
                pos_count = sum(1 for w in positive_keywords if w in news_text)
                neg_count = sum(1 for w in negative_keywords if w in news_text)
                
                # 給分邏輯：標題正向關鍵字多於負向關鍵字
                if pos_count > neg_count:
                    scores['media'] = 0.80
                elif neg_count > pos_count:
                    scores['media'] = 0.30

        except Exception as e:
            print(f"股票 {stock_id} 運算指標時發生錯誤: {e}")

    # 確保分數落在 0.0 到 1.0 之間
    for k in scores:
        scores[k] = min(max(scores[k], 0.0), 1.0)

    # 綜合計算最終預測分數 forecast_score (自訂各指標權重)
    # 權重設定：技術面30%、籌碼面30%、基本面20%、主力10%、新聞10%
    final_score = (scores['twse_tpex'] * 0.30 + 
                   scores['fininst'] * 0.30 + 
                   scores['mops'] * 0.20 + 
                   scores['vendor'] * 0.10 + 
                   scores['media'] * 0.10)
                   
    # 決定買賣訊號
    signal = "BUY" if final_score >= 0.40 else "HOLD"
    
    return {
        "stock_id": stock_id,
        "forecast_score": final_score,
        "signal": signal,
        "market_multiplier": 1.0,
        "sub_scores": scores
    }
