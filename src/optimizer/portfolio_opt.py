import numpy as np

class PortfolioOptimizer:
    def __init__(self, tsmc_limit=0.25, other_limit=0.10):
        self.tsmc_limit = tsmc_limit
        self.other_limit = other_limit

    def optimize_weights(self, stock_ids: list, forecast_scores: list) -> dict:
        """根據 AI 分數與競賽上限平滑分配權重"""
        n = len(stock_ids)
        if n == 0:
            return {}
            
        weights = {}
        # 簡易示範：按分數比例權重並帶入上限 Constraints
        raw_weights = np.array(forecast_scores) / sum(forecast_scores)
        
        for idx, s_id in enumerate(stock_ids):
            limit = self.tsmc_limit if s_id == "2330" else self.other_limit
            weights[s_id] = min(raw_weights[idx], limit)
            
        return weights
