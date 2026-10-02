class RiskManager:
    """交易風險管理模組"""
    def __init__(self, stop_loss_pct: float = 0.07, stop_profit_pct: float = 0.15, max_position_size: float = 0.2):
        self.stop_loss_pct = stop_loss_pct      # 個股硬停損比例 (例如 7%)
        self.stop_profit_pct = stop_profit_pct  # 停利目標比例 (例如 15%)
        self.max_position_size = max_position_size # 單一個股持股上限比例 (例如 20%)

    def check_stop_loss_profit(self, entry_price: float, current_price: float) -> str:
        """檢查是否達到停損或停利點"""
        returns = (current_price - entry_price) / entry_price
        
        if returns <= -self.stop_loss_pct:
            return "STOP_LOSS"
        elif returns >= self.stop_profit_pct:
            return "STOP_PROFIT"
        return "HOLD"

    def adjust_weight_by_risk(self, target_weight: float) -> float:
        """確保單一股票配置不超過設定上限"""
        return min(target_weight, self.max_position_size)
