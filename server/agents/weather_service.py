"""
WeatherService - 天气服务

根据游戏时间（季节、时辰）和地点生成合理的天气与气象信息。
天气会自然演化，剧变时通知订阅者。
"""

import random
import threading
import time
from typing import Callable, List, Optional

from gm_logger import debug_log, info_log, warn_log, error_log


# 季节定义
SEASONS = {
    1: "春", 2: "春", 3: "春",
    4: "夏", 5: "夏", 6: "夏",
    7: "秋", 8: "秋", 9: "秋",
    10: "冬", 11: "冬", 12: "冬",
}

# 基础天气池：(天气主类型, 天气描述)
WEATHER_POOL = {
    "春": [
        ("晴朗", "微风和煦"),
        ("晴朗", "春光明媚"),
        ("多云", "薄云遮日"),
        ("小雨", "春雨绵绵"),
        ("小雨", "细雨如丝"),
        ("薄雾", "晨雾朦胧"),
    ],
    "夏": [
        ("晴朗", "烈日当空"),
        ("晴朗", "骄阳似火"),
        ("多云", "云层厚重"),
        ("雷阵雨", "电闪雷鸣"),
        ("暴雨", "大雨倾盆"),
        ("炎热", "暑气蒸腾"),
    ],
    "秋": [
        ("晴朗", "秋高气爽"),
        ("晴朗", "天高云淡"),
        ("多云", "层云漫漫"),
        ("凉风", "秋风萧瑟"),
        ("秋雨", "秋雨淅沥"),
        ("薄雾", "秋雾弥漫"),
    ],
    "冬": [
        ("晴朗", "冬日暖阳"),
        ("晴朗", "寒空万里"),
        ("多云", "阴云密布"),
        ("小雪", "雪花飘洒"),
        ("大雪", "鹅毛大雪"),
        ("寒风", "北风呼啸"),
    ],
}

# 夜间天气描述覆盖（白天描述 -> 夜间描述）
NIGHT_DESC_OVERRIDES = {
    "微风和煦": "晚风轻柔",
    "春光明媚": "月色温柔",
    "烈日当空": "星光璀璨",
    "骄阳似火": "月朗星稀",
    "暑气蒸腾": "夜凉如水",
    "秋高气爽": "月华如练",
    "天高云淡": "星河灿烂",
    "秋风萧瑟": "夜风清冷",
    "冬日暖阳": "寒夜静谧",
    "寒空万里": "满天星斗",
    "薄云遮日": "薄云遮月",
    "云层厚重": "云幕低垂",
    "层云漫漫": "层云蔽月",
    "阴云密布": "夜色沉沉",
}


class WeatherService:
    """
    天气服务

    根据游戏时间（季节、时辰）生成合理的天气。
    每游戏日有一定概率天气变化，支持订阅通知。
    """

    # 天气演化检查间隔（游戏分钟）：每 120 游戏分钟检查一次
    EVOLVE_INTERVAL = 120

    def __init__(self, storage, world_time_service=None):
        """
        初始化天气服务

        Args:
            storage: GMStorage 实例，用于数据库读写
            world_time_service: WorldTimeService 实例，用于获取游戏时间
        """
        self._storage = storage
        self._world_time_service = world_time_service
        self._lock = threading.Lock()

        # 天气状态
        self._weather: str = "晴朗"
        self._weather_desc: str = "微风"
        self._spirit_tide: bool = False
        self._spirit_tide_intensity: int = 0

        # 游戏时间快照（用于检测时间推进）
        self._last_game_day: int = 0
        self._last_game_hour: int = 0
        self._last_game_minute: int = 0
        self._last_real_timestamp: float = 0.0

        # 累积推进的游戏分钟（用于触发演化检查）
        self._accumulated_minutes: int = 0

        # SSE 订阅回调列表
        self._subscribers: List[Callable] = []

        # 后台线程控制
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

        # 从数据库恢复
        self._load_from_db()

        # 初始化时间快照
        self._update_time_snapshot()

    def _get_season(self, month: int) -> str:
        """根据月份获取季节"""
        return SEASONS.get(month, "春")

    def _is_night(self, hour: int) -> bool:
        """判断是否为夜间（21-5时）"""
        return hour >= 21 or hour <= 5

    def _generate_weather(self, game_month: int, game_hour: int) -> tuple:
        """
        根据季节和时辰生成天气

        Args:
            game_month: 游戏月份 1-12
            game_hour: 游戏小时 0-23

        Returns:
            (weather, weather_desc) 元组
        """
        season = self._get_season(game_month)
        pool = WEATHER_POOL.get(season, WEATHER_POOL["春"])
        weather, desc = random.choice(pool)

        # 夜间覆盖描述
        if self._is_night(game_hour):
            desc = NIGHT_DESC_OVERRIDES.get(desc, desc)

        return weather, desc

    def _check_spirit_tide(self, game_day: int) -> tuple:
        """
        检查灵潮状态

        Args:
            game_day: 游戏日 1-30

        Returns:
            (spirit_tide, intensity) 元组
        """
        if game_day == 15:
            return True, random.randint(2, 5)
        return False, 0

    def _load_from_db(self) -> None:
        """从数据库恢复天气状态"""
        try:
            weather_data = self._storage.couch_get_weather()
            if weather_data and "weather" in weather_data:
                self._weather = weather_data["weather"]
                self._weather_desc = weather_data.get("weather_desc", "微风")
                self._spirit_tide = weather_data.get("spirit_tide", False)
                self._spirit_tide_intensity = weather_data.get("spirit_tide_intensity", 0)
                self._last_game_day = weather_data.get("game_day", 0)
                self._last_game_hour = weather_data.get("game_hour", 0)
                self._last_game_minute = weather_data.get("game_minute", 0)
                self._last_real_timestamp = weather_data.get("real_timestamp", 0.0)
                info_log(
                    f"天气状态从数据库恢复: {self._weather}·{self._weather_desc}, "
                    f"灵潮={self._spirit_tide}"
                )
            else:
                # 首次初始化
                self._init_default_weather()
        except Exception as e:
            error_log(f"从数据库恢复天气状态失败: {e}，使用默认天气")
            self._init_default_weather()

    def _init_default_weather(self) -> None:
        """初始化默认天气"""
        self._weather = "晴朗"
        self._weather_desc = "微风"
        self._spirit_tide = False
        self._spirit_tide_intensity = 0
        info_log("天气状态初始化为默认值: 晴朗·微风")
        self._save_to_db()

    def _save_to_db(self) -> None:
        """保存天气状态到数据库"""
        try:
            weather_data = {
                "_id": "weather_state",
                "weather": self._weather,
                "weather_desc": self._weather_desc,
                "spirit_tide": self._spirit_tide,
                "spirit_tide_intensity": self._spirit_tide_intensity,
                "game_day": self._last_game_day,
                "game_hour": self._last_game_hour,
                "game_minute": self._last_game_minute,
                "real_timestamp": time.time(),
            }
            self._storage.couch_save_weather(weather_data)
            debug_log(f"天气状态已保存: {self._weather}·{self._weather_desc}")
        except Exception as e:
            error_log(f"保存天气状态失败: {e}")

    def _update_time_snapshot(self) -> None:
        """更新时间快照"""
        if self._world_time_service:
            try:
                time_info = self._world_time_service.get_current_time()
                self._last_game_day = time_info.get("game_day", 1)
                self._last_game_hour = time_info.get("game_hour", 0)
                self._last_game_minute = time_info.get("game_minute", 0)
            except Exception:
                pass

    def _tick(self) -> None:
        """天气演化检查

        注意：锁仅保护内存状态的读写，I/O 操作（数据库保存、通知订阅者）
        在锁外执行，避免持锁时因网络阻塞导致死锁。
        """
        if not self._world_time_service:
            return

        need_save = False
        need_notify = False
        weather_info = None

        with self._lock:
            try:
                time_info = self._world_time_service.get_current_time()
                current_day = time_info.get("game_day", 1)
                current_hour = time_info.get("game_hour", 0)
                current_minute = time_info.get("game_minute", 0)

                # 检测日期变化 -> 天气变化
                if current_day != self._last_game_day:
                    self._last_game_day = current_day
                    self._last_game_hour = current_hour
                    self._last_game_minute = current_minute
                    self._accumulated_minutes = 0

                    old_weather = self._weather
                    old_desc = self._weather_desc

                    # 重新生成天气
                    self._weather, self._weather_desc = self._generate_weather(
                        time_info.get("game_month", 1), current_hour
                    )
                    self._spirit_tide, self._spirit_tide_intensity = self._check_spirit_tide(current_day)

                    info_log(
                        f"天气变化: {old_weather}·{old_desc} -> "
                        f"{self._weather}·{self._weather_desc}, 灵潮={self._spirit_tide}"
                    )

                    need_save = True
                    need_notify = True
                    weather_info = self._get_current_weather_locked()
                else:
                    # 同一天内，偶尔微调
                    self._accumulated_minutes += 1
                    if self._accumulated_minutes >= self.EVOLVE_INTERVAL:
                        self._accumulated_minutes = 0
                        if random.random() < 0.3:  # 30% 概率微调
                            old_desc = self._weather_desc
                            # 根据当前时辰微调描述
                            _, new_desc = self._generate_weather(
                                time_info.get("game_month", 1), current_hour
                            )
                            # 保持主天气不变，只更新描述
                            if new_desc != self._weather_desc:
                                self._weather_desc = new_desc
                                debug_log(f"天气描述微调: {old_desc} -> {self._weather_desc}")
                                need_save = True

            except Exception as e:
                error_log(f"天气演化检查异常: {e}")

        # 在锁外执行 I/O 操作，避免持锁时因网络阻塞导致死锁
        if need_save:
            self._save_to_db()

        if need_notify and weather_info:
            self._notify_subscribers(weather_info)

    def _run_loop(self) -> None:
        """后台线程主循环"""
        info_log("天气服务后台线程启动")
        while self._running:
            try:
                self._tick()
            except Exception as e:
                error_log(f"天气演化异常: {e}")
            # 每 30 秒检查一次（真实时间）
            time.sleep(30)
        info_log("天气服务后台线程停止")

    def get_current_weather(self) -> dict:
        """
        获取当前天气信息

        Returns:
            天气信息字典，包含 weather、weather_desc、spirit_tide、spirit_tide_intensity
        """
        with self._lock:
            return self._get_current_weather_locked()

    def _get_current_weather_locked(self) -> dict:
        """
        获取当前天气信息（调用方必须已持有 self._lock）

        Returns:
            天气信息字典
        """
        return {
            "weather": self._weather,
            "weather_desc": self._weather_desc,
            "spirit_tide": self._spirit_tide,
            "spirit_tide_intensity": self._spirit_tide_intensity,
        }

    def subscribe(self, callback: Callable) -> None:
        """
        订阅天气变化事件

        Args:
            callback: 回调函数，接收天气信息字典作为参数
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)
            info_log(f"新增天气变化订阅者，当前订阅者数量: {len(self._subscribers)}")

    def unsubscribe(self, callback: Callable) -> None:
        """
        取消订阅天气变化事件

        Args:
            callback: 要移除的回调函数
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            info_log(f"移除天气变化订阅者，当前订阅者数量: {len(self._subscribers)}")

    def _notify_subscribers(self, weather_info: dict) -> None:
        """通知所有订阅者天气变化"""
        for callback in self._subscribers:
            try:
                callback(weather_info)
            except Exception as e:
                error_log(f"通知天气变化订阅者失败: {e}")

        # 同时发布到全局 EventBus，供统一 SSE 使用
        try:
            from event_bus import get_event_bus
            get_event_bus().publish("weather_change", weather_info)
        except Exception as e:
            error_log(f"发布天气变化到 EventBus 失败: {e}")

    def start(self) -> None:
        """启动后台天气演化线程"""
        if self._running:
            warn_log("天气服务已在运行中，忽略重复启动")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="weather-service",
            daemon=True,
        )
        self._thread.start()
        info_log("天气服务已启动")

    def stop(self) -> None:
        """停止后台天气演化线程"""
        if not self._running:
            return

        self._running = False
        # 保存最终天气状态
        self._save_to_db()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                warn_log("天气服务线程未能在5秒内停止")

        info_log("天气服务已停止")


# ───────────────────────────────────────────────
# 全局单例引用（供其他模块直接获取实例，避免循环依赖）
# ───────────────────────────────────────────────

_weather_service_instance: Optional["WeatherService"] = None


def set_weather_service(instance: "WeatherService"):
    """设置全局 WeatherService 实例"""
    global _weather_service_instance
    _weather_service_instance = instance


def get_weather_service_instance() -> Optional["WeatherService"]:
    """获取全局 WeatherService 实例"""
    return _weather_service_instance
