class PortfolioOptimizer:
    def __init__(self, score_threshold: float = 0.45):
        self.score_threshold = score_threshold

    def decide_trade_action(self, stock_id: str, eval_res: dict, current_holdings: dict) -> dict:
        """
        根據評分結果與當前庫存判定下單動作
        """
        score = eval_res["forecast_score"]
        sub_scores = eval_res["sub_scores"]
        shares_held = current_holdings.get(stock_id, {}).get("shares", 0)

        # 防禦機制：基本面或籌碼面過差時禁止買進/加碼
        if sub_scores["mops"] < 0.4 or sub_scores["fininst"] < 0.35:
            return {"action": "SKIP", "target_lots": 0, "reason": "基本面(mops)或籌碼面(fininst)表現過差"}

        if score >= self.score_threshold:
            if shares_held == 0:
                return {"action": "BUY_INITIAL", "target_lots": 2, "reason": f"分數 {score} 達標，執行初始建倉"}
            else:
                return {"action": "ADD_POSITION", "target_lots": 1, "reason": f"分數 {score} 達標，執行庫存加碼"}
        else:
            return {"action": "HOLD_OR_SELL", "target_lots": 0, "reason": f"分數 {score} 未達評分門檻 {self.score_threshold}"}
