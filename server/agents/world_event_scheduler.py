"""
WorldEventScheduler - 世界事件定时调度器

后台守护线程，定期触发世界演化（world_tick），
生成世界事件并通过 EventBus 推送到前端，同时触发布局更新。

用法:
    from world_event_scheduler import WorldEventScheduler

    scheduler = WorldEventScheduler(storage, game_master, config)
    scheduler.start()   # 启动后台线程

    scheduler.stop()    # 停止后台线程
"""

import time
import threading
from typing import Optional

from gm_logger import debug_log, info_log, warn_log, error_log


class WorldEventScheduler:
    """
    世界事件定时调度器

    后台守护线程，定期调用 GameMaster.world_tick_task() 触发世界演化，
    将生成的世界事件和布局变化通过 EventBus 推送到前端。
    """

    # 默认调度间隔（秒）：1小时
    DEFAULT_INTERVAL = 3600

    def __init__(self, storage, game_master, config: dict):
        """
        初始化世界事件调度器

        Args:
            storage: GMStorage 实例，用于数据库读写
            game_master: GameMaster 实例，用于调用世界演化任务
            config: 配置字典，读取 gm.world_tick.interval_seconds
        """
        self._storage = storage
        self._game_master = game_master
        self._config = config
        self._lock = threading.Lock()

        # 从配置读取调度间隔
        gm_cfg = config.get("gm", {})
        world_tick_cfg = gm_cfg.get("world_tick", {})
        self._interval = world_tick_cfg.get("interval_seconds", self.DEFAULT_INTERVAL)

        # 后台线程控制
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

        info_log(f"世界事件调度器初始化: 间隔={self._interval}秒")

    def _tick(self) -> None:
        """
        执行一次世界演化

        调用 GameMaster.world_tick_task() 生成世界事件，
        将结果中的 world_events 和 layout_hint 发布到 EventBus。
        """
        info_log("世界事件调度: 开始执行世界演化任务...")

        try:
            # 调用世界演化任务
            result = self._game_master.world_tick_task()

            if not result:
                warn_log("世界事件调度: world_tick_task 返回空结果")
                return

            # 提取 ui_config 中的事件和布局提示
            ui_config = result.get("ui_config", {})
            world_events = ui_config.get("world_events", [])
            layout_hint = ui_config.get("layout_hint")

            # 发布 world_event 到 EventBus
            if isinstance(world_events, list) and world_events:
                try:
                    from event_bus import get_event_bus
                    for evt in world_events:
                        if isinstance(evt, dict):
                            get_event_bus().publish("world_event", evt)
                    info_log(f"世界事件调度: 发布 {len(world_events)} 个世界事件到 EventBus")
                except Exception as e:
                    error_log(f"世界事件调度: 发布 world_event 到 EventBus 失败: {e}")

            # 发布 layout_change 到 EventBus
            if layout_hint:
                try:
                    from event_bus import get_event_bus
                    get_event_bus().publish("layout_change", {"panel_type": layout_hint})
                    info_log(f"世界事件调度: 发布 layout_change 事件: panel_type={layout_hint}")
                except Exception as e:
                    error_log(f"世界事件调度: 发布 layout_change 到 EventBus 失败: {e}")

            info_log("世界事件调度: 世界演化任务完成")

        except Exception as e:
            error_log(f"世界事件调度: 执行世界演化任务异常: {e}")

    def _run_loop(self) -> None:
        """后台线程主循环"""
        info_log(f"世界事件调度器后台线程启动, 间隔={self._interval}秒")
        while self._running:
            try:
                self._tick()
            except Exception as e:
                error_log(f"世界事件调度异常: {e}")

            # 每次执行完成后才 sleep，避免 LLM 调用耗时导致间隔漂移
            time.sleep(self._interval)

        info_log("世界事件调度器后台线程停止")

    def start(self) -> None:
        """启动后台调度线程"""
        if self._running:
            warn_log("世界事件调度器已在运行中，忽略重复启动")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="world-event-scheduler",
            daemon=True,
        )
        self._thread.start()
        info_log("世界事件调度器已启动")

    def stop(self) -> None:
        """停止后台调度线程"""
        if not self._running:
            return

        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                warn_log("世界事件调度器线程未能在5秒内停止")

        info_log("世界事件调度器已停止")


# ───────────────────────────────────────────────
# 全局单例引用（供其他模块直接获取实例，避免循环依赖）
# ───────────────────────────────────────────────

_world_event_scheduler_instance: Optional["WorldEventScheduler"] = None


def set_world_event_scheduler(instance: "WorldEventScheduler"):
    """设置全局 WorldEventScheduler 实例"""
    global _world_event_scheduler_instance
    _world_event_scheduler_instance = instance


def get_world_event_scheduler_instance() -> Optional["WorldEventScheduler"]:
    """获取全局 WorldEventScheduler 实例"""
    return _world_event_scheduler_instance
