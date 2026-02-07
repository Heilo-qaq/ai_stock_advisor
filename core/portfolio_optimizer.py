"""
组合优化模块
Markowitz均值-方差优化、相关性分析、行业分散化
"""
import pandas as pd
import numpy as np
from scipy.optimize import minimize
import config


class PortfolioOptimizer:
    """投资组合优化器"""
    
    def __init__(self):
        self.max_single_weight = config.MAX_SINGLE_POSITION
        self.max_sector_weight = config.MAX_SECTOR_EXPOSURE
    
    def optimize(self, returns_df: pd.DataFrame, method: str = "max_sharpe",
                 risk_free_rate: float = 0.03) -> dict:
        """
        组合优化
        
        Args:
            returns_df: 各股票日收益率DataFrame (columns=股票代码)
            method: "max_sharpe" | "min_variance" | "risk_parity"
            risk_free_rate: 无风险利率
        
        Returns:
            {
                'weights': dict,        # {code: weight}
                'expected_return': float,
                'expected_volatility': float,
                'sharpe_ratio': float,
                'correlation_matrix': DataFrame,
            }
        """
        if returns_df.empty or len(returns_df.columns) < 2:
            # 单只股票直接全配
            if len(returns_df.columns) == 1:
                code = returns_df.columns[0]
                return {'weights': {code: 1.0}}
            return {'weights': {}}
        
        # 计算协方差矩阵和预期收益
        cov_matrix = returns_df.cov() * 252
        mean_returns = returns_df.mean() * 252
        n = len(returns_df.columns)
        
        if method == "max_sharpe":
            weights = self._max_sharpe(mean_returns, cov_matrix, risk_free_rate)
        elif method == "min_variance":
            weights = self._min_variance(cov_matrix)
        elif method == "risk_parity":
            weights = self._risk_parity(cov_matrix)
        else:
            weights = np.ones(n) / n
        
        # 计算组合指标
        port_return = np.dot(weights, mean_returns)
        port_vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))
        sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0
        
        weight_dict = {col: w for col, w in zip(returns_df.columns, weights)}
        
        return {
            'weights': weight_dict,
            'expected_return': port_return,
            'expected_volatility': port_vol,
            'sharpe_ratio': sharpe,
            'correlation_matrix': returns_df.corr(),
        }
    
    def _max_sharpe(self, mean_returns, cov_matrix, rf):
        """最大夏普比率组合"""
        n = len(mean_returns)
        
        def neg_sharpe(w):
            ret = np.dot(w, mean_returns)
            vol = np.sqrt(np.dot(w, np.dot(cov_matrix, w)))
            return -(ret - rf) / vol if vol > 0 else 0
        
        constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]
        bounds = [(0, self.max_single_weight) for _ in range(n)]
        init = np.ones(n) / n
        
        result = minimize(neg_sharpe, init, method='SLSQP',
                          bounds=bounds, constraints=constraints)
        return result.x if result.success else init
    
    def _min_variance(self, cov_matrix):
        """最小方差组合"""
        n = len(cov_matrix)
        
        def portfolio_var(w):
            return np.dot(w, np.dot(cov_matrix, w))
        
        constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]
        bounds = [(0, self.max_single_weight) for _ in range(n)]
        init = np.ones(n) / n
        
        result = minimize(portfolio_var, init, method='SLSQP',
                          bounds=bounds, constraints=constraints)
        return result.x if result.success else init
    
    def _risk_parity(self, cov_matrix):
        """风险平价"""
        n = len(cov_matrix)
        
        def risk_budget_obj(w):
            port_vol = np.sqrt(np.dot(w, np.dot(cov_matrix, w)))
            if port_vol == 0:
                return 0
            marginal_risk = np.dot(cov_matrix, w) / port_vol
            risk_contrib = w * marginal_risk
            target = port_vol / n
            return np.sum((risk_contrib - target) ** 2)
        
        constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]
        bounds = [(0.01, self.max_single_weight) for _ in range(n)]
        init = np.ones(n) / n
        
        result = minimize(risk_budget_obj, init, method='SLSQP',
                          bounds=bounds, constraints=constraints)
        return result.x if result.success else init
    
    def check_correlation(self, returns_df: pd.DataFrame, threshold: float = 0.7) -> list:
        """
        检查高相关性股票对
        
        Returns:
            [(stock1, stock2, correlation), ...] 相关性超过阈值的股票对
        """
        if returns_df.empty or len(returns_df.columns) < 2:
            return []
        
        corr = returns_df.corr()
        high_corr_pairs = []
        
        cols = corr.columns
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                c = corr.iloc[i, j]
                if abs(c) >= threshold:
                    high_corr_pairs.append((cols[i], cols[j], c))
        
        return sorted(high_corr_pairs, key=lambda x: abs(x[2]), reverse=True)
    
    def generate_efficient_frontier(self, returns_df: pd.DataFrame,
                                     n_points: int = 50) -> pd.DataFrame:
        """
        生成有效前沿
        用于可视化风险-收益权衡
        """
        cov_matrix = returns_df.cov() * 252
        mean_returns = returns_df.mean() * 252
        n = len(returns_df.columns)
        
        # 找到最小和最大收益率
        min_ret = mean_returns.min()
        max_ret = mean_returns.max()
        
        target_returns = np.linspace(min_ret, max_ret, n_points)
        frontier = []
        
        for target in target_returns:
            constraints = [
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1},
                {'type': 'eq', 'fun': lambda w, t=target: np.dot(w, mean_returns) - t},
            ]
            bounds = [(0, self.max_single_weight) for _ in range(n)]
            init = np.ones(n) / n
            
            def portfolio_var(w):
                return np.dot(w, np.dot(cov_matrix, w))
            
            result = minimize(portfolio_var, init, method='SLSQP',
                              bounds=bounds, constraints=constraints)
            
            if result.success:
                vol = np.sqrt(result.fun)
                frontier.append({'return': target, 'volatility': vol})
        
        return pd.DataFrame(frontier)
