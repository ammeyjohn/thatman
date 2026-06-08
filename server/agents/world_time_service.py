"""
WorldTimeService - 世界定时服务

以 10:1 时间比例推进游戏时间（1 真实分钟 = 10 游戏分钟）。
每个时辰变化后保存到数据库，并通知前端。

时间推进规则：
- 每 6 秒真实时间推进 1 游戏分钟（6秒 × 10倍 = 60秒游戏时间）
- 每 12 分钟真实时间推进 1 个时辰（2 游戏小时）
- 每天 12 个时辰，每 2.4 小时真实时间推进 1 游戏天

用法:
    from world_time_service import WorldTimeService

    service = WorldTimeService(storage)
    service.start()   # 启动后台线程

    # 获取当前游戏时间
    time_info = service.get_current_time()

    # 订阅时辰变化
    service.subscribe(callback)

    service.stop()    # 停止后台线程
"""

import time
import threading
from typing import Callable, List, Optional

from gm_logger import debug_log, info_log, warn_log, error_log


# ───────────────────────────────────────────────
# 中文数字转换辅助函数
# ───────────────────────────────────────────────

# 数字到中文的映射
_DIGITS_CN = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
_UNITS_CN = ["", "十", "百", "千", "万"]


def _number_to_chinese(num: int) -> str:
    """
    将整数转换为中文数字表示

    支持 0-99999 范围，用于年份转换。

    Args:
        num: 整数

    Returns:
        中文数字字符串

    示例:
        0   -> "零"
        1   -> "一"
        10  -> "十"
        12  -> "十二"
        100 -> "一百"
        3600 -> "三千六百"
        10000 -> "一万"
    """
    if num == 0:
        return "零"

    if num < 0:
        return "负" + _number_to_chinese(-num)

    result = ""

    # 万位
    if num >= 10000:
        wan_part = num // 10000
        result += _number_to_chinese(wan_part) + "万"
        num = num % 10000
        if num == 0:
            return result
        # 万位后如果千位为0需要补零
        if num < 1000:
            result += "零"

    # 千位
    if num >= 1000:
        qian = num // 1000
        result += _DIGITS_CN[qian] + "千"
        num = num % 1000
        if num == 0:
            return result
        # 千位后如果百位为0需要补零
        if num < 100:
            result += "零"

    # 百位
    if num >= 100:
        bai = num // 100
        result += _DIGITS_CN[bai] + "百"
        num = num % 100
        if num == 0:
            return result
        # 百位后如果十位为0需要补零
        if num < 10:
            result += "零"

    # 十位和个位
    if num >= 10:
        shi = num // 10
        # 10-19 不需要前面的"一"，直接"十X"
        if shi > 1 or result:
            result += _DIGITS_CN[shi] + "十"
        else:
            result += "十"
        num = num % 10

    if num > 0:
        result += _DIGITS_CN[num]

    return result


def _month_to_chinese(month: int) -> str:
    """
    将月份数字转换为中文表示

    Args:
        month: 月份 1-12

    Returns:
        中文月份字符串

    示例:
        1  -> "正月"
        2  -> "二月"
        12 -> "十二月"
    """
    _MONTH_NAMES = [
        "正月", "二月", "三月", "四月", "五月", "六月",
        "七月", "八月", "九月", "十月", "十一月", "十二月",
    ]
    if 1 <= month <= 12:
        return _MONTH_NAMES[month - 1]
    return f"{month}月"


def _day_to_chinese(day: int) -> str:
    """
    将日数字转换为中文表示

    Args:
        day: 日 1-30

    Returns:
        中文日字符串

    示例:
        1  -> "初一"
        10 -> "初十"
        11 -> "十一"
        20 -> "二十"
        21 -> "二十一"
        30 -> "三十"
    """
    if 1 <= day <= 10:
        if day == 10:
            return "初十"
        return "初" + _DIGITS_CN[day]
    elif 11 <= day <= 19:
        return "十" + _DIGITS_CN[day - 10]
    elif day == 20:
        return "二十"
    elif 21 <= day <= 29:
        return "二十" + _DIGITS_CN[day - 20]
    elif day == 30:
        return "三十"
    return f"{day}日"


# ───────────────────────────────────────────────
# 时辰映射
# ───────────────────────────────────────────────

# 12 时辰定义：(名称, 时段描述, 起始小时, 结束小时)
# 注意：子时跨日（23-1时），特殊处理
SHICHEN_LIST = [
    {"name": "子时", "period": "深夜", "start": 23, "end": 1},   # 23-1时
    {"name": "丑时", "period": "凌晨", "start": 1,  "end": 3},   # 1-3时
    {"name": "寅时", "period": "黎明", "start": 3,  "end": 5},   # 3-5时
    {"name": "卯时", "period": "清晨", "start": 5,  "end": 7},   # 5-7时
    {"name": "辰时", "period": "早晨", "start": 7,  "end": 9},   # 7-9时
    {"name": "巳时", "period": "上午", "start": 9,  "end": 11},  # 9-11时
    {"name": "午时", "period": "正午", "start": 11, "end": 13},  # 11-13时
    {"name": "未时", "period": "午后", "start": 13, "end": 15},  # 13-15时
    {"name": "申时", "period": "下午", "start": 15, "end": 17},  # 15-17时
    {"name": "酉时", "period": "黄昏", "start": 17, "end": 19},  # 17-19时
    {"name": "戌时", "period": "傍晚", "start": 19, "end": 21},  # 19-21时
    {"name": "亥时", "period": "夜晚", "start": 21, "end": 23},  # 21-23时
]


def _get_shichen(hour: int) -> dict:
    """
    根据小时获取时辰信息

    Args:
        hour: 游戏小时 0-23

    Returns:
        时辰信息字典，包含 name, period, index
    """
    # 子时跨日：23时和0时都属于子时
    if hour == 23 or hour == 0:
        return {"name": "子时", "period": "深夜", "index": 0}

    # 其他时辰：按小时范围匹配
    for idx, sc in enumerate(SHICHEN_LIST):
        if sc["start"] <= hour < sc["end"]:
            return {"name": sc["name"], "period": sc["period"], "index": idx}

    # 兜底（不应到达）
    return {"name": "子时", "period": "深夜", "index": 0}


# ───────────────────────────────────────────────
# WorldTimeService
# ───────────────────────────────────────────────

class WorldTimeService:
    """
    世界定时服务

    以 10:1 时间比例推进游戏时间（1 真实分钟 = 10 游戏分钟）。
    每 6 秒推进 1 游戏分钟，每 12 分钟真实时间推进 1 个时辰。
    时辰变化时保存到数据库并通知所有订阅者。
    """

    # 时间推进间隔（秒）：6秒真实时间 = 1游戏分钟
    TICK_INTERVAL = 6
    # 时间比例：1 真实分钟 = 10 游戏分钟
    TIME_RATIO = 10
    # 默认初始游戏年份
    DEFAULT_YEAR = 3600

    def __init__(self, storage):
        """
        初始化世界时间服务

        Args:
            storage: GMStorage 实例，用于数据库读写
        """
        self._storage = storage
        self._lock = threading.Lock()

        # 游戏时间状态
        self._game_year: int = self.DEFAULT_YEAR
        self._game_month: int = 1
        self._game_day: int = 1
        self._game_hour: int = 0
        self._game_minute: int = 0
        self._real_timestamp: float = 0.0

        # 当前时辰索引（用于变化检测）
        self._current_shichen_index: int = 0

        # SSE 订阅回调列表
        self._subscribers: List[Callable] = []

        # 后台线程控制
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

        # 从数据库恢复时间状态
        self._load_from_db()

    def _load_from_db(self) -> None:
        """从数据库恢复时间状态"""
        try:
            time_data = self._storage.couch_get_world_time()
            if time_data and "game_year" in time_data:
                # 数据库中有记录，恢复时间状态
                self._game_year = time_data["game_year"]
                self._game_month = time_data["game_month"]
                self._game_day = time_data["game_day"]
                self._game_hour = time_data["game_hour"]
                self._game_minute = time_data["game_minute"]
                self._real_timestamp = time_data.get("real_timestamp", 0.0)

                # 根据真实时间差计算当前游戏时间
                now = time.time()
                if self._real_timestamp > 0:
                    real_elapsed = now - self._real_timestamp
                    # 计算游戏时间经过的分钟数
                    game_minutes_elapsed = int(real_elapsed / 60 * self.TIME_RATIO)
                    if game_minutes_elapsed > 0:
                        info_log(f"数据库恢复时间状态，补进 {game_minutes_elapsed} 游戏分钟 "
                                 f"(真实经过 {real_elapsed:.1f} 秒)")
                        self._advance_time(game_minutes_elapsed)

                # 更新当前时辰索引
                shichen = _get_shichen(self._game_hour)
                self._current_shichen_index = shichen["index"]

                info_log(f"世界时间从数据库恢复: "
                         f"{self._format_game_date()} {shichen['name']}·{shichen['period']} "
                         f"{self._game_hour:02d}:{self._game_minute:02d}")
            else:
                # 数据库中无记录，使用默认初始时间
                self._game_year = self.DEFAULT_YEAR
                self._game_month = 1
                self._game_day = 1
                self._game_hour = 0
                self._game_minute = 0
                self._real_timestamp = time.time()
                self._current_shichen_index = 0

                info_log(f"世界时间初始化为默认值: {self._format_game_date()} 子时·深夜 00:00")
                # 保存初始状态到数据库
                self._save_to_db()

        except Exception as e:
            error_log(f"从数据库恢复时间状态失败: {e}，使用默认值")
            self._game_year = self.DEFAULT_YEAR
            self._game_month = 1
            self._game_day = 1
            self._game_hour = 0
            self._game_minute = 0
            self._real_timestamp = time.time()
            self._current_shichen_index = 0

    def _save_to_db(self) -> None:
        """保存当前时间状态到数据库"""
        try:
            time_data = {
                "_id": "world_time_state",
                "game_year": self._game_year,
                "game_month": self._game_month,
                "game_day": self._game_day,
                "game_hour": self._game_hour,
                "game_minute": self._game_minute,
                "real_timestamp": time.time(),
                "time_ratio": self.TIME_RATIO,
            }
            self._storage.couch_save_world_time(time_data)
            debug_log(f"世界时间已保存到数据库: {self._format_game_date()} "
                      f"{self._game_hour:02d}:{self._game_minute:02d}")
        except Exception as e:
            error_log(f"保存世界时间到数据库失败: {e}")

    def _advance_time(self, minutes: int) -> None:
        """
        推进游戏时间指定分钟数

        Args:
            minutes: 要推进的游戏分钟数
        """
        total_minutes = self._game_hour * 60 + self._game_minute + minutes

        # 计算新的小时和分钟
        hours_to_add = total_minutes // 60
        self._game_minute = total_minutes % 60

        # 计算需要推进的天数
        days_to_add = hours_to_add // 24
        self._game_hour = hours_to_add % 24

        if days_to_add > 0:
            self._advance_days(days_to_add)

    def _advance_days(self, days: int) -> None:
        """
        推进游戏时间指定天数

        Args:
            days: 要推进的天数
        """
        self._game_day += days

        # 处理月份溢出
        while self._game_day > 30:
            self._game_day -= 30
            self._game_month += 1

        # 处理年份溢出
        while self._game_month > 12:
            self._game_month -= 12
            self._game_year += 1

    def _format_game_date(self) -> str:
        """
        格式化游戏日期为中文表示

        Returns:
            格式如 "天元三千六百年·正月初一"
        """
        year_cn = _number_to_chinese(self._game_year)
        month_cn = _month_to_chinese(self._game_month)
        day_cn = _day_to_chinese(self._game_day)
        return f"天元{year_cn}年·{month_cn}{day_cn}"

    def _tick(self) -> None:
        """
        时间推进一次

        每 6 秒调用一次，推进 1 游戏分钟。
        检测时辰变化，变化时保存数据库并通知订阅者。
        """
        with self._lock:
            # 记录推进前的时辰
            old_shichen = _get_shichen(self._game_hour)

            # 推进 1 游戏分钟
            self._advance_time(1)

            # 检测时辰是否变化
            new_shichen = _get_shichen(self._game_hour)

            if new_shichen["index"] != old_shichen["index"]:
                info_log(f"时辰变化: {old_shichen['name']}·{old_shichen['period']} -> "
                         f"{new_shichen['name']}·{new_shichen['period']} "
                         f"({self._format_game_date()} {self._game_hour:02d}:{self._game_minute:02d})")

                # 更新当前时辰索引
                self._current_shichen_index = new_shichen["index"]

                # 保存到数据库
                self._save_to_db()

                # 通知所有订阅者
                time_info = self.get_current_time()
                self._notify_subscribers(time_info)
            else:
                self._current_shichen_index = new_shichen["index"]
                debug_log(f"时间推进: {self._format_game_date()} "
                          f"{self._game_hour:02d}:{self._game_minute:02d} "
                          f"({new_shichen['name']}·{new_shichen['period']})")

    def _notify_subscribers(self, time_info: dict) -> None:
        """
        通知所有订阅者时辰变化

        Args:
            time_info: 当前时间信息字典
        """
        for callback in self._subscribers:
            try:
                callback(time_info)
            except Exception as e:
                error_log(f"通知时辰变化订阅者失败: {e}")

    def _run_loop(self) -> None:
        """后台线程主循环"""
        info_log("世界时间服务后台线程启动")
        while self._running:
            try:
                self._tick()
            except Exception as e:
                error_log(f"时间推进异常: {e}")

            # 按间隔休眠
            time.sleep(self.TICK_INTERVAL)

        info_log("世界时间服务后台线程停止")

    def get_current_time(self) -> dict:
        """
        获取当前游戏时间信息

        Returns:
            时间信息字典，包含游戏日期、时辰、时间比例等
        """
        with self._lock:
            shichen = _get_shichen(self._game_hour)
            return {
                "game_date": self._format_game_date(),
                "game_year": self._game_year,
                "game_month": self._game_month,
                "game_day": self._game_day,
                "game_hour": self._game_hour,
                "game_minute": self._game_minute,
                "shichen_name": shichen["name"],
                "shichen_period": shichen["period"],
                "shichen_index": shichen["index"],
                "time_ratio": self.TIME_RATIO,
            }

    def subscribe(self, callback: Callable) -> None:
        """
        订阅时辰变化事件

        当时辰变化时，会调用 callback(time_info) 通知订阅者。

        Args:
            callback: 回调函数，接收时间信息字典作为参数
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)
            info_log(f"新增时辰变化订阅者，当前订阅者数量: {len(self._subscribers)}")

    def unsubscribe(self, callback: Callable) -> None:
        """
        取消订阅时辰变化事件

        Args:
            callback: 要移除的回调函数
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            info_log(f"移除时辰变化订阅者，当前订阅者数量: {len(self._subscribers)}")

    def start(self) -> None:
        """启动后台时间推进线程"""
        if self._running:
            warn_log("世界时间服务已在运行中，忽略重复启动")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="world-time-service",
            daemon=True,
        )
        self._thread.start()
        info_log("世界时间服务已启动")

    def stop(self) -> None:
        """停止后台时间推进线程"""
        if not self._running:
            return

        self._running = False
        # 保存最终时间状态
        self._save_to_db()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                warn_log("世界时间服务线程未能在5秒内停止")

        info_log("世界时间服务已停止")


# ───────────────────────────────────────────────
# 全局单例引用（供其他模块直接获取实例，避免循环依赖）
# ───────────────────────────────────────────────

_world_time_service_instance: Optional["WorldTimeService"] = None


def set_world_time_service(instance: "WorldTimeService"):
    """设置全局 WorldTimeService 实例"""
    global _world_time_service_instance
    _world_time_service_instance = instance


def get_world_time_service_instance() -> Optional["WorldTimeService"]:
    """获取全局 WorldTimeService 实例"""
    return _world_time_service_instance
