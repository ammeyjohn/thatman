"""
EventBus - 线程安全的事件发布订阅总线

供 WorldTimeService、WeatherService、GM 路由等模块使用，
将服务端自主发生的事件统一汇集，通过 SSE 推送到前端。

支持三种推送模式：
1. 全局广播 publish() — 所有订阅者收到
2. 定向推送 publish_to_uid() — 仅指定 uid 的订阅者收到
3. 频道推送 publish_to_channel() — 订阅了该频道的订阅者收到

用法:
    from event_bus import get_event_bus

    bus = get_event_bus()

    # 全局订阅（兼容旧逻辑）
    q = bus.subscribe()
    event = q.get(timeout=30)

    # 按 uid 订阅（SSE 连接绑定用户）
    q = bus.subscribe(uid="user_123")

    # 订阅频道（如区域频道）
    q = bus.subscribe_channel("area:云溪村")

    # 全局广播
    bus.publish("layout_change", {"panel_type": "both"})

    # 定向推送
    bus.publish_to_uid("user_123", "private_message", {"from": "user_456", "content": "..."})

    # 频道推送
    bus.publish_to_channel("area:云溪村", "area_message", {"from": "user_123", "content": "..."})
"""

import queue
import threading
from typing import Dict, Any, List, Optional, Set

from gm_logger import debug_log, info_log, error_log


class EventBus:
    """线程安全的事件总线，支持全局广播、uid 定向推送和频道订阅"""

    def __init__(self):
        # 全局订阅者（兼容旧逻辑）
        self._subscribers: List[queue.Queue] = []
        # 按 uid 订阅：uid -> queue
        self._uid_subscribers: Dict[str, queue.Queue] = {}
        # 按频道订阅：channel -> [queue, ...]
        self._channel_subscribers: Dict[str, List[queue.Queue]] = {}
        # 反向索引：queue -> 订阅信息（用于 unsubscribe 时清理）
        self._queue_info: Dict[int, dict] = {}  # id(q) -> {"uid": str|None, "channels": [str]}
        self._lock = threading.Lock()

    def subscribe(self, uid: str = None) -> queue.Queue:
        """
        订阅事件

        Args:
            uid: 可选，绑定用户 uid，用于接收定向推送

        Returns:
            queue.Queue: 事件队列，订阅者通过该队列接收事件
        """
        q = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
            if uid:
                self._uid_subscribers[uid] = q
            self._queue_info[id(q)] = {"uid": uid, "channels": []}

        info_log(f"EventBus 新增订阅者, uid={uid}, 当前全局订阅者数量: {len(self._subscribers)}")
        return q

    def subscribe_channel(self, channel: str) -> queue.Queue:
        """
        订阅特定频道

        Args:
            channel: 频道名称，如 "area:云溪村"

        Returns:
            queue.Queue: 事件队列
        """
        q = queue.Queue()
        with self._lock:
            if channel not in self._channel_subscribers:
                self._channel_subscribers[channel] = []
            self._channel_subscribers[channel].append(q)
            self._queue_info[id(q)] = {"uid": None, "channels": [channel]}

        debug_log(f"EventBus 新增频道订阅: channel={channel}")
        return q

    def add_channel_subscription(self, q: queue.Queue, channel: str) -> None:
        """
        为已有的订阅队列添加频道订阅

        Args:
            q: 已有的订阅队列
            channel: 频道名称
        """
        with self._lock:
            if channel not in self._channel_subscribers:
                self._channel_subscribers[channel] = []
            if q not in self._channel_subscribers[channel]:
                self._channel_subscribers[channel].append(q)
            qid = id(q)
            if qid in self._queue_info:
                if channel not in self._queue_info[qid]["channels"]:
                    self._queue_info[qid]["channels"].append(channel)

        debug_log(f"EventBus 添加频道订阅: channel={channel}")

    def remove_channel_subscription(self, q: queue.Queue, channel: str) -> None:
        """
        移除订阅队列的频道订阅

        Args:
            q: 已有的订阅队列
            channel: 频道名称
        """
        with self._lock:
            if channel in self._channel_subscribers:
                if q in self._channel_subscribers[channel]:
                    self._channel_subscribers[channel].remove(q)
                if not self._channel_subscribers[channel]:
                    del self._channel_subscribers[channel]
            qid = id(q)
            if qid in self._queue_info:
                if channel in self._queue_info[qid]["channels"]:
                    self._queue_info[qid]["channels"].remove(channel)

        debug_log(f"EventBus 移除频道订阅: channel={channel}")

    def unsubscribe(self, q: queue.Queue) -> None:
        """
        取消订阅（自动从所有订阅列表中移除）

        Args:
            q: 要移除的事件队列
        """
        with self._lock:
            # 从全局订阅者移除
            if q in self._subscribers:
                self._subscribers.remove(q)

            # 从 uid 订阅移除
            qid = id(q)
            info = self._queue_info.pop(qid, {})
            uid = info.get("uid")
            if uid and self._uid_subscribers.get(uid) is q:
                del self._uid_subscribers[uid]

            # 从频道订阅移除
            channels = info.get("channels", [])
            for channel in channels:
                if channel in self._channel_subscribers:
                    if q in self._channel_subscribers[channel]:
                        self._channel_subscribers[channel].remove(q)
                    if not self._channel_subscribers[channel]:
                        del self._channel_subscribers[channel]

        info_log(f"EventBus 移除订阅者, uid={uid}, 当前全局订阅者数量: {len(self._subscribers)}")

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        发布事件到所有订阅者（全局广播）

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
                debug_log("EventBus 订阅者队列已满，跳过")
            except Exception as e:
                error_log(f"EventBus 发布事件到订阅者失败: {e}")

        debug_log(f"EventBus 全局广播: {event_type}, 订阅者数={len(subscribers)}")

    def publish_to_uid(self, uid: str, event_type: str, data: Dict[str, Any]) -> None:
        """
        定向推送给指定用户

        Args:
            uid: 目标用户 uid
            event_type: 事件类型
            data: 事件数据字典
        """
        event = {"type": event_type, "data": data}
        with self._lock:
            q = self._uid_subscribers.get(uid)

        if q:
            try:
                q.put(event, timeout=1)
                debug_log(f"EventBus 定向推送: uid={uid}, event={event_type}")
            except queue.Full:
                debug_log(f"EventBus 定向推送失败，队列已满: uid={uid}")
            except Exception as e:
                error_log(f"EventBus 定向推送失败: uid={uid}, 错误={e}")
        else:
            debug_log(f"EventBus 定向推送跳过，用户不在线: uid={uid}")

    def publish_to_channel(self, channel: str, event_type: str, data: Dict[str, Any]) -> None:
        """
        推送到频道

        Args:
            channel: 频道名称，如 "area:云溪村"
            event_type: 事件类型
            data: 事件数据字典
        """
        event = {"type": event_type, "data": data}
        with self._lock:
            subscribers = self._channel_subscribers.get(channel, [])[:]

        for subscriber_q in subscribers:
            try:
                subscriber_q.put(event, timeout=1)
            except queue.Full:
                debug_log(f"EventBus 频道推送跳过，队列已满: channel={channel}")
            except Exception as e:
                error_log(f"EventBus 频道推送失败: channel={channel}, 错误={e}")

        debug_log(f"EventBus 频道推送: channel={channel}, event={event_type}, 订阅者数={len(subscribers)}")

    def get_uid_for_queue(self, q: queue.Queue) -> Optional[str]:
        """获取队列绑定的 uid"""
        with self._lock:
            info = self._queue_info.get(id(q))
            return info.get("uid") if info else None


# 模块级单例
_event_bus_instance: EventBus = EventBus()


def get_event_bus() -> EventBus:
    """获取 EventBus 单例实例"""
    return _event_bus_instance
