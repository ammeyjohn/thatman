"""
PriceManager - 世界均价管理器

基于物品品级和类型计算世界平均价格，支撑坊市交易的默认定价。
品级基准价参考 item_config.md 定义，GM可通过工具动态调整。

用法:
    from price_manager import get_price_manager

    mgr = get_price_manager()
    price = mgr.get_average_price("灵草", "材料", "凡品")
    # 返回 4 (凡品基准5 × 材料0.8)
"""

import threading
from typing import Dict, Optional

from gm_logger import debug_log, info_log, warn_log, error_log


# ───────────────────────────────────────────────
# 品级基准价（下品灵石）
# ───────────────────────────────────────────────

GRADE_BASE_PRICES: Dict[str, int] = {
    "凡品": 5,
    "良品": 50,
    "上品": 500,
    "极品": 5000,
    "上古品": 50000,
}

# ───────────────────────────────────────────────
# 类型价格系数
# ───────────────────────────────────────────────

TYPE_PRICE_FACTORS: Dict[str, float] = {
    "丹药": 1.2,
    "法宝": 1.5,
    "符箓": 1.1,
    "阵法": 1.3,
    "材料": 0.8,
    "天材地宝": 2.0,
    "装备": 1.0,
    "武器": 1.2,
    "防具": 1.0,
    "辅助": 0.9,
    "其他": 1.0,
}

# 品级关键词映射
GRADE_KEYWORDS: Dict[str, str] = {
    "凡品": "凡品",
    "凡": "凡品",
    "良品": "良品",
    "良": "良品",
    "上品": "上品",
    "上": "上品",
    "极品": "极品",
    "极": "极品",
    "上古品": "上古品",
    "上古": "上古品",
}


class PriceManager:
    """世界均价管理器（线程安全）"""

    def __init__(self):
        self._custom_prices: Dict[str, int] = {}  # item_id -> 自定义均价
        self._lock = threading.Lock()

    def get_average_price(
        self,
        name: str = "",
        item_type: str = "其他",
        grade: str = "凡品",
        item_id: str = "",
    ) -> int:
        """
        获取物品世界平均价格（下品灵石）

        优先级：自定义价格 > 品级×类型计算

        Args:
            name: 物品名称
            item_type: 物品类型（丹药/法宝/材料等）
            grade: 物品品级（凡品/良品/上品/极品/上古品）
            item_id: 物品ID

        Returns:
            世界均价（下品灵石），最低1
        """
        # 1. 检查自定义价格
        if item_id:
            with self._lock:
                if item_id in self._custom_prices:
                    return self._custom_prices[item_id]

        # 2. 解析品级
        resolved_grade = self._resolve_grade(grade)

        # 3. 基于品级和类型计算
        base_price = GRADE_BASE_PRICES.get(resolved_grade, 5)
        type_factor = TYPE_PRICE_FACTORS.get(item_type, 1.0)
        price = max(1, int(base_price * type_factor))

        debug_log(f"均价计算: name={name}, type={item_type}, grade={grade}({resolved_grade}), price={price}")
        return price

    def set_custom_price(self, item_id: str, price: int) -> None:
        """
        设置物品自定义均价

        Args:
            item_id: 物品ID
            price: 自定义均价（下品灵石）
        """
        if price < 1:
            warn_log(f"自定义均价不能小于1: item_id={item_id}, price={price}")
            price = 1

        with self._lock:
            self._custom_prices[item_id] = price
        info_log(f"自定义均价已设置: item_id={item_id}, price={price}")

    def remove_custom_price(self, item_id: str) -> bool:
        """
        移除物品自定义均价，恢复公式计算

        Args:
            item_id: 物品ID

        Returns:
            是否成功移除
        """
        with self._lock:
            if item_id in self._custom_prices:
                del self._custom_prices[item_id]
                info_log(f"自定义均价已移除: item_id={item_id}")
                return True
        return False

    def get_all_custom_prices(self) -> Dict[str, int]:
        """获取所有自定义均价"""
        with self._lock:
            return dict(self._custom_prices)

    def _resolve_grade(self, grade: str) -> str:
        """
        解析品级字符串，支持模糊匹配

        Args:
            grade: 品级字符串

        Returns:
            标准品级名称
        """
        if not grade:
            return "凡品"

        # 精确匹配
        if grade in GRADE_BASE_PRICES:
            return grade

        # 关键词匹配
        for keyword, resolved in GRADE_KEYWORDS.items():
            if keyword in grade:
                return resolved

        # 默认凡品
        return "凡品"


# ───────────────────────────────────────────────
# 全局单例
# ───────────────────────────────────────────────

_price_manager_instance: Optional[PriceManager] = None


def get_price_manager() -> PriceManager:
    """
    获取 PriceManager 单例实例

    Returns:
        PriceManager 实例
    """
    global _price_manager_instance
    if _price_manager_instance is None:
        _price_manager_instance = PriceManager()
    return _price_manager_instance
