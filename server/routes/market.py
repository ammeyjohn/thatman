"""
市场路由 - 处理灵石查询、摊位CRUD、交易等坊市功能
"""

import logging
import sys
from pathlib import Path

from flask import Blueprint, request, jsonify

# 将 agents 目录添加到路径
agents_path = Path(__file__).parent.parent / "agents"
if str(agents_path) not in sys.path:
    sys.path.insert(0, str(agents_path))

from gm_logger import debug_log, info_log, error_log
from routes.auth import _verify_token

# 配置日志
logger = logging.getLogger(__name__)

market_bp = Blueprint('market', __name__)


def _get_uid_from_request() -> str:
    """从请求中获取 uid（优先从 token 解析，其次从参数获取）"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        payload = _verify_token(token)
        if payload and payload.get('uid'):
            return payload['uid']

    data = request.get_json(silent=True) or {}
    uid = data.get('uid', '') or request.args.get('uid', '')
    return uid


def _verify_auth() -> tuple:
    """验证认证，返回 (uid, error_response)"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return '', (jsonify({
            'error': {'message': '未授权访问', 'type': 'authentication_error', 'code': 'unauthorized'}
        }), 401)

    token = auth_header[7:]
    payload = _verify_token(token)
    if not payload:
        return '', (jsonify({
            'error': {'message': '未授权访问', 'type': 'authentication_error', 'code': 'unauthorized'}
        }), 401)

    uid = request.args.get('uid', '') or (request.get_json(silent=True) or {}).get('uid', '')
    if not uid:
        return '', (jsonify({
            'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400)

    return uid, None


def _get_stall_manager():
    """获取 StallManager 实例"""
    from stall_manager import get_stall_manager
    mgr = get_stall_manager()

    # 确保 storage 已设置
    if not mgr._storage:
        try:
            from game_master import GameMaster
            gm = GameMaster()
            if gm.storage:
                mgr.set_storage(gm.storage)
        except Exception as e:
            error_log(f"设置 StallManager storage 失败: {e}")

    return mgr


# ───────────────────────────────────────────────
# 灵石查询
# ───────────────────────────────────────────────

@market_bp.route('/market/spirit-stones', methods=['GET'])
def get_spirit_stones():
    """
    查询玩家灵石余额

    查询参数:
        uid: 玩家唯一ID（必填）

    响应格式:
    {
        "uid": "user_123",
        "spirit_stones": {
            "low": 100,
            "medium": 5,
            "high": 0,
            "top": 0
        }
    }
    """
    uid, err = _verify_auth()
    if err:
        return err

    try:
        mgr = _get_stall_manager()
        result = mgr.get_spirit_stones(uid)

        if "error" in result:
            return jsonify({
                'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'query_failed'}
            }), 400

        return jsonify(result)

    except Exception as e:
        error_log(f"查询灵石余额失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


# ───────────────────────────────────────────────
# 摊位 CRUD
# ───────────────────────────────────────────────

@market_bp.route('/market/stall', methods=['GET'])
def get_my_stall():
    """
    查询自己的摊位

    查询参数:
        uid: 玩家唯一ID（必填）

    响应格式:
    {
        "stall": { ... } 或 null
    }
    """
    uid, err = _verify_auth()
    if err:
        return err

    try:
        mgr = _get_stall_manager()
        stall = mgr.get_stall_by_owner(uid)

        return jsonify({
            'uid': uid,
            'stall': stall,
        })

    except Exception as e:
        error_log(f"查询摊位失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


@market_bp.route('/market/stall', methods=['POST'])
def create_stall():
    """
    创建摊位

    请求体:
    {
        "uid": "玩家uid",
        "stall_name": "摊位名称",
        "items": [
            {
                "item_id": "herb_001",
                "name": "灵草",
                "type": "材料",
                "description": "普通灵草",
                "quantity": 10,
                "price": 5  // 可选，不指定则使用世界均价
            }
        ]
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({
            'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400

    uid = data.get('uid', '')
    stall_name = data.get('stall_name', '')
    items = data.get('items', [])

    if not uid:
        return jsonify({
            'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400

    try:
        mgr = _get_stall_manager()
        result = mgr.create_stall(uid, stall_name, items)

        if "error" in result:
            return jsonify({
                'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'create_failed'}
            }), 400

        return jsonify(result)

    except Exception as e:
        error_log(f"创建摊位失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


@market_bp.route('/market/stall', methods=['DELETE'])
def close_stall():
    """
    关闭摊位

    请求体:
    {
        "uid": "玩家uid"
    }
    """
    data = request.get_json() or {}
    uid = data.get('uid', '') or request.args.get('uid', '')

    if not uid:
        return jsonify({
            'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400

    try:
        mgr = _get_stall_manager()
        result = mgr.close_stall(uid)

        if "error" in result:
            return jsonify({
                'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'close_failed'}
            }), 400

        return jsonify(result)

    except Exception as e:
        error_log(f"关闭摊位失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


@market_bp.route('/market/stalls', methods=['GET'])
def get_stalls():
    """
    获取当前位置的摊位列表

    查询参数:
        uid: 玩家唯一ID（必填，用于确定当前位置）
        location: 位置名称（可选，不指定则使用玩家当前位置）

    响应格式:
    {
        "location": "云溪村坊市",
        "stalls": [ ... ]
    }
    """
    uid, err = _verify_auth()
    if err:
        return err

    location = request.args.get('location', '')

    try:
        mgr = _get_stall_manager()

        # 如果没有指定位置，从玩家数据获取
        if not location:
            from gm_storage import GMStorage
            try:
                from game_master import GameMaster
                gm = GameMaster()
                if gm.storage:
                    player_data = gm.storage.couch_get_player(uid)
                    location = player_data.get("current_location", "") if player_data else ""
            except Exception:
                pass

        if not location:
            return jsonify({
                'location': '',
                'stalls': [],
            })

        stalls = mgr.get_stalls_by_location(location)

        return jsonify({
            'location': location,
            'stalls': stalls,
        })

    except Exception as e:
        error_log(f"获取摊位列表失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


@market_bp.route('/market/stall/<stall_id>', methods=['GET'])
def get_stall_detail(stall_id):
    """
    获取指定摊位详情

    路径参数:
        stall_id: 摊位ID

    响应格式:
    {
        "stall": { ... }
    }
    """
    try:
        mgr = _get_stall_manager()
        stall = mgr.get_stall(stall_id)

        if not stall:
            return jsonify({
                'error': {'message': '摊位不存在或已关闭', 'type': 'invalid_request_error', 'code': 'not_found'}
            }), 404

        return jsonify({
            'stall': stall,
        })

    except Exception as e:
        error_log(f"获取摊位详情失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


# ───────────────────────────────────────────────
# 交易操作
# ───────────────────────────────────────────────

@market_bp.route('/market/trade/buy', methods=['POST'])
def buy_from_stall():
    """
    从摊位购买物品

    请求体:
    {
        "uid": "买家uid",
        "stall_id": "摊位ID",
        "item_id": "物品ID",
        "quantity": 1
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({
            'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400

    uid = data.get('uid', '')
    stall_id = data.get('stall_id', '')
    item_id = data.get('item_id', '')
    quantity = data.get('quantity', 1)

    if not uid:
        return jsonify({
            'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400

    try:
        mgr = _get_stall_manager()
        result = mgr.buy_item(uid, stall_id, item_id, quantity)

        if "error" in result:
            return jsonify({
                'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'buy_failed'}
            }), 400

        return jsonify(result)

    except Exception as e:
        error_log(f"购买物品失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


@market_bp.route('/market/trade/sell', methods=['POST'])
def sell_to_stall():
    """
    向摊位出售物品

    请求体:
    {
        "uid": "卖家uid",
        "stall_id": "摊位ID",
        "item_id": "物品ID",
        "quantity": 1,
        "price": 5  // 可选，不指定则使用世界均价
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({
            'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400

    uid = data.get('uid', '')
    stall_id = data.get('stall_id', '')
    item_id = data.get('item_id', '')
    quantity = data.get('quantity', 1)
    price = data.get('price')

    if not uid:
        return jsonify({
            'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}
        }), 400

    try:
        mgr = _get_stall_manager()
        result = mgr.sell_to_stall(uid, stall_id, item_id, quantity, price)

        if "error" in result:
            return jsonify({
                'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'sell_failed'}
            }), 400

        return jsonify(result)

    except Exception as e:
        error_log(f"出售物品失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500


# ───────────────────────────────────────────────
# 物品均价查询
# ───────────────────────────────────────────────

@market_bp.route('/market/item-price', methods=['GET'])
def get_item_price():
    """
    查询物品世界均价

    查询参数:
        name: 物品名称
        type: 物品类型（可选）
        grade: 物品品级（可选）
        item_id: 物品ID（可选）

    响应格式:
    {
        "price": 5,
        "name": "灵草",
        "type": "材料",
        "grade": "凡品"
    }
    """
    name = request.args.get('name', '')
    item_type = request.args.get('type', '其他')
    grade = request.args.get('grade', '凡品')
    item_id = request.args.get('item_id', '')

    try:
        from price_manager import get_price_manager
        price_mgr = get_price_manager()
        price = price_mgr.get_average_price(name=name, item_type=item_type, grade=grade, item_id=item_id)

        return jsonify({
            'price': price,
            'name': name,
            'type': item_type,
            'grade': grade,
        })

    except Exception as e:
        error_log(f"查询物品均价失败: {e}")
        return jsonify({
            'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}
        }), 500
