from src.data_loader.finmind_loader import FinMindDataLoader
from src.models.dynamic_forecast import ai_dynamic_forecast
from src.optimizer.portfolio_opt import PortfolioOptimizer

def main():
    print("=========================================================")
    print("  AI CUP 2026 玉山人工智慧挑戰賽 - AI Agent Fund Manager")
    print("=========================================================\n")
    
    # 1. 初始化資料載入器 (內建帶 Token 與 Fallback 備用機制)
    loader = FinMindDataLoader()
    optimizer = PortfolioOptimizer()
    
    # 2. 設定追蹤的目標股票與基準權重 (Benchmark)
    target_stocks = ["2330", "2317", "2454"]
    benchmark_weights = {"2330": 0.50, "2317": 0.30, "2454": 0.20}
    
    forecast_results = []
    print(">>> 步驟 1: 即時從網路抓取三大法人籌碼與股價並進行 AI 動態分析預測...")
    
    for stock_id in target_stocks:
        # 動態預測會自動調用 loader 抓取最新股價與籌碼
        forecast = ai_dynamic_forecast(stock_id, loader=loader)
        forecast_results.append(forecast)
        
        details = forecast.get("analysis_details", {})
        print(f"[{stock_id}] 預測得分: {forecast['forecast_score']} | 訊號: {forecast['signal']}")
        print(f"       -> 動量分數: {details.get('momentum_score')} | 籌碼 Z-Score: {details.get('chip_z_score')}")

    print("\n>>> 步驟 2: 進行投資組合權重最佳化與 Active Share 風控計算...")
    final_portfolio = optimizer.optimize_weights(forecast_results, benchmark_weights)
    
    print("\n================ 最終建議配置權重 ================")
    for stock, weight in final_portfolio.items():
        print(f" 股票 {stock} : {weight * 100:.2f}%")
    print("==================================================")

if __name__ == "__main__":
    main()
