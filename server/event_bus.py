"""
EventBus - 线程安全的事件发布订阅总线

供 WorldTimeService、WeatherService、GM 路由等模块使用，
将服务端自主发生的事件统一汇集，通过 SSE 推送到前端。

用法:
    from event_bus import get_event_bus

    bus = get_event_bus()
    q = bus.subscribe()
    try:
        event = q.get(timeout=30)  # {"type": "time_change", "data": {...}}
    finally:
        bus.unsubscribe(q)

    # 发布事件
    bus.publish("layout_change", {"panel_type": "both"})
"""

import queue
import threading
from typing import Dict, Any, List

from gm_logger import debug_log, info_log, error_log


class EventBus:
    """线程安全的事件总线"""

    def __init__(self):
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        """
        订阅事件

        Returns:
            queue.Queue: 事件队列，订阅者通过该队列接收事件
        """
        q = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        info_log(f"EventBus 新增订阅者，当前订阅者数量: {len(self._subscribers)}")
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """
        取消订阅

        Args:
            q: 要移除的事件队列
        """
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)
                info_log(f"EventBus 移除订阅者，当前订阅者数量: {len(self._subscribers)}")

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        发布事件到所有订阅者

        Args:
            event_type: 事件类型，如 "time_change", "weather_change", "layout_change"
            data: 事件数据字典
        """
        event = {"type": event_type, "data": data}
        with self._lock:
            subscribers = self._subscribers[:]

        for subscriber_q in subscribers:
            try:
                subscriber_q.put(event, timeout=1)
            except queue.Full:
                debug_log(f"EventBus 订阅者队列已满，跳过")
            except Exception as e:
                error_log(f"EventBus 发布事件到订阅者失败: {e}")

        debug_log(f"EventBus 发布事件: {event_type}, 订阅者数={len(subscribers)}")


# 模块级单例
_event_bus_instance: EventBus = EventBus()


def get_event_bus() -> EventBus:
    """获取 EventBus 单例实例"""
    return _event_bus_instance
