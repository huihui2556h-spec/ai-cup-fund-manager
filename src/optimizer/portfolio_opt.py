import numpy as np
import pandas as pd
from scipy.optimize import minimize

class PortfolioOptimizer:
    def __init__(self, returns_df: pd.DataFrame, risk_free_rate: float = 0.015):
        self.returns = returns_df
        self.rf = risk_free_rate

    def optimize_max_sharpe(self) -> dict:
        """計算最大夏普比率的資產配置權重"""
        num_assets = self.returns.shape[1]
        mean_returns = self.returns.mean() * 252
        cov_matrix = self.returns.cov() * 252

        def negative_sharpe(weights):
            p_return = np.sum(mean_returns * weights)
            p_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            return -(p_return - self.rf) / p_volatility

        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        bounds = tuple((0, 1) for _ in range(num_assets))
        initial_weights = num_assets * [1. / num_assets]

        result = minimize(negative_sharpe, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        
        return dict(zip(self.returns.columns, np.round(result.x, 4)))
