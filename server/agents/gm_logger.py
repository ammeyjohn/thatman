"""
GM 日志工具模块

提供统一日志函数，受 gm.debug 配置开关控制。
所有 GM 模块（game_master、gm_storage、gm_tools）共享此模块，
避免循环导入问题。
"""

import logging

logger = logging.getLogger(__name__)

# GM debug 开关，从 config.yaml gm.debug 读取，默认 True
_gm_debug: bool = True


def set_debug(enabled: bool) -> None:
    """设置 debug 开关"""
    global _gm_debug
    _gm_debug = enabled


def is_debug() -> bool:
    """获取 debug 开关状态"""
    return _gm_debug


def debug_log(message: str):
    """输出 DEBUG 级别日志（灰色），受 gm.debug 配置控制"""
    logger.debug(message)
    if _gm_debug:
        print(f"\033[90m[DEBUG] {message}\033[0m")


def info_log(message: str):
    """输出 INFO 级别日志（白色）"""
    logger.info(message)
    print(f"\033[97m[INFO] {message}\033[0m")


def warn_log(message: str):
    """输出 WARN 级别日志（黄色）"""
    logger.warning(message)
    print(f"\033[93m[WARN] {message}\033[0m")


def error_log(message: str):
    """输出 ERROR 级别日志（红色）"""
    logger.error(message)
    print(f"\033[91m[ERROR] {message}\033[0m")
