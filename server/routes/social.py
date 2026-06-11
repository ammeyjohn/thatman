"""
社交路由 - 处理玩家间聊天、好友、组队、交易、切磋等社交功能
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

social_bp = Blueprint('social', __name__)


def _get_uid_from_request() -> str:
    """从请求中获取 uid（优先从 token 解析，其次从参数获取）"""
    # 尝试从 Authorization header 获取
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        payload = _verify_token(token)
        if payload and payload.get('uid'):
            return payload['uid']

    # 从请求参数获取
    data = request.get_json(silent=True) or {}
    uid = data.get('uid', '') or request.args.get('uid', '')
    return uid


# ───────────────────────────────────────────────
# 私聊消息
# ───────────────────────────────────────────────

@social_bp.route('/social/message/send', methods=['POST'])
def send_private_message():
    """
    发送私聊消息

    请求体:
    {
        "uid": "发送者uid",
        "to_uid": "接收者uid",
        "content": "消息内容"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    to_uid = data.get('to_uid', '')
    content = data.get('content', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400
    if not to_uid:
        return jsonify({'error': {'message': 'to_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400
    if not content or not content.strip():
        return jsonify({'error': {'message': '消息内容不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from chat_manager import get_chat_manager
        chat_mgr = get_chat_manager()
        result = chat_mgr.send_private_message(uid, to_uid, content)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'send_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"发送私聊消息失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/message/history', methods=['GET'])
def get_private_message_history():
    """
    获取私聊记录

    查询参数:
        uid: 当前用户uid
        peer_uid: 对方uid
        limit: 返回条数（默认50）
    """
    uid = request.args.get('uid', '')
    peer_uid = request.args.get('peer_uid', '')
    limit = int(request.args.get('limit', '50'))

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400
    if not peer_uid:
        return jsonify({'error': {'message': 'peer_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from chat_manager import get_chat_manager
        chat_mgr = get_chat_manager()
        messages = chat_mgr.get_private_messages(uid, peer_uid, limit=limit)
        return jsonify({'uid': uid, 'peer_uid': peer_uid, 'messages': messages})
    except Exception as e:
        error_log(f"获取私聊记录失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 区域消息
# ───────────────────────────────────────────────

@social_bp.route('/social/area-message', methods=['POST'])
def send_area_message():
    """
    发送区域消息

    请求体:
    {
        "uid": "发送者uid",
        "content": "消息内容",
        "location": "区域位置（可选，不传则从玩家数据获取）"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    content = data.get('content', '')
    location = data.get('location', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400
    if not content or not content.strip():
        return jsonify({'error': {'message': '消息内容不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from chat_manager import get_chat_manager
        chat_mgr = get_chat_manager()
        result = chat_mgr.send_area_message(uid, content, location=location)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'send_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"发送区域消息失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/area-messages', methods=['GET'])
def get_area_messages():
    """
    获取区域聊天记录

    查询参数:
        location: 区域位置
        limit: 返回条数（默认50）
    """
    location = request.args.get('location', '')
    limit = int(request.args.get('limit', '50'))

    if not location:
        return jsonify({'error': {'message': 'location 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from chat_manager import get_chat_manager
        chat_mgr = get_chat_manager()
        messages = chat_mgr.get_area_messages(location, limit=limit)
        return jsonify({'location': location, 'messages': messages})
    except Exception as e:
        error_log(f"获取区域聊天记录失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 联系人
# ───────────────────────────────────────────────

@social_bp.route('/social/contacts', methods=['GET'])
def get_chat_contacts():
    """
    获取聊天联系人列表

    查询参数:
        uid: 当前用户uid
    """
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from chat_manager import get_chat_manager
        chat_mgr = get_chat_manager()
        contacts = chat_mgr.get_chat_contacts(uid)
        return jsonify({'uid': uid, 'contacts': contacts})
    except Exception as e:
        error_log(f"获取聊天联系人失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 好友系统
# ───────────────────────────────────────────────

@social_bp.route('/social/friend/request', methods=['POST'])
def send_friend_request():
    """
    发送好友申请

    请求体:
    {
        "uid": "发送者uid",
        "target_uid": "目标uid"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    if uid == target_uid:
        return jsonify({'error': {'message': '不能添加自己为好友', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.send_friend_request(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'request_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"发送好友申请失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/friend/accept', methods=['POST'])
def accept_friend_request():
    """
    接受好友申请

    请求体:
    {
        "uid": "接受者uid",
        "from_uid": "申请者uid"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    from_uid = data.get('from_uid', '')

    if not uid or not from_uid:
        return jsonify({'error': {'message': 'uid 和 from_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.accept_friend_request(uid, from_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'accept_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"接受好友申请失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/friend/reject', methods=['POST'])
def reject_friend_request():
    """
    拒绝好友申请

    请求体:
    {
        "uid": "拒绝者uid",
        "from_uid": "申请者uid"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    from_uid = data.get('from_uid', '')

    if not uid or not from_uid:
        return jsonify({'error': {'message': 'uid 和 from_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.reject_friend_request(uid, from_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'reject_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"拒绝好友申请失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/friends', methods=['GET'])
def get_friends():
    """
    获取好友列表

    查询参数:
        uid: 当前用户uid
    """
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        friends = social_mgr.get_friends(uid)
        return jsonify({'uid': uid, 'friends': friends})
    except Exception as e:
        error_log(f"获取好友列表失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/friend/requests', methods=['GET'])
def get_friend_requests():
    """
    获取待处理的好友申请

    查询参数:
        uid: 当前用户uid
    """
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        requests = social_mgr.get_friend_requests(uid)
        return jsonify({'uid': uid, 'requests': requests})
    except Exception as e:
        error_log(f"获取好友申请列表失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/friend/<target_uid>', methods=['DELETE'])
def delete_friend(target_uid):
    """
    删除好友

    查询参数:
        uid: 当前用户uid
    """
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.delete_friend(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'delete_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"删除好友失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 师徒系统
# ───────────────────────────────────────────────

@social_bp.route('/social/master/request', methods=['POST'])
def send_master_request():
    """发送拜师请求"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.send_master_request(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'request_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"发送拜师请求失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/master/accept', methods=['POST'])
def accept_master_request():
    """接受拜师请求"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    from_uid = data.get('from_uid', '')

    if not uid or not from_uid:
        return jsonify({'error': {'message': 'uid 和 from_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.accept_master_request(uid, from_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'accept_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"接受拜师请求失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/master/break', methods=['POST'])
def break_master_relation():
    """解除师徒关系"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.break_master_relation(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'break_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"解除师徒关系失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/master/info', methods=['GET'])
def get_master_info():
    """获取师徒信息"""
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        info = social_mgr.get_master_info(uid)
        return jsonify({'uid': uid, 'master_info': info})
    except Exception as e:
        error_log(f"获取师徒信息失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 道侣系统
# ───────────────────────────────────────────────

@social_bp.route('/social/companion/request', methods=['POST'])
def send_companion_request():
    """发送结为道侣请求"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.send_companion_request(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'request_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"发送道侣请求失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/companion/accept', methods=['POST'])
def accept_companion_request():
    """接受道侣请求"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    from_uid = data.get('from_uid', '')

    if not uid or not from_uid:
        return jsonify({'error': {'message': 'uid 和 from_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.accept_companion_request(uid, from_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'accept_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"接受道侣请求失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/companion/break', methods=['POST'])
def break_companion_relation():
    """解除道侣关系"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        result = social_mgr.break_companion_relation(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'break_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"解除道侣关系失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/companion/info', methods=['GET'])
def get_companion_info():
    """获取道侣信息"""
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from social_manager import get_social_manager
        social_mgr = get_social_manager()
        info = social_mgr.get_companion_info(uid)
        return jsonify({'uid': uid, 'companion_info': info})
    except Exception as e:
        error_log(f"获取道侣信息失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 组队系统
# ───────────────────────────────────────────────

@social_bp.route('/social/team/create', methods=['POST'])
def create_team():
    """创建队伍"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from team_manager import get_team_manager
        team_mgr = get_team_manager()
        result = team_mgr.create_team(uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'create_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"创建队伍失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/team/invite', methods=['POST'])
def invite_team_member():
    """邀请入队"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from team_manager import get_team_manager
        team_mgr = get_team_manager()
        result = team_mgr.invite_member(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'invite_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"邀请入队失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/team/accept', methods=['POST'])
def accept_team_invite():
    """接受入队邀请"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    team_id = data.get('team_id', '')

    if not uid or not team_id:
        return jsonify({'error': {'message': 'uid 和 team_id 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from team_manager import get_team_manager
        team_mgr = get_team_manager()
        result = team_mgr.accept_invite(uid, team_id)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'accept_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"接受入队邀请失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/team/leave', methods=['POST'])
def leave_team():
    """离开队伍"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from team_manager import get_team_manager
        team_mgr = get_team_manager()
        result = team_mgr.leave_team(uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'leave_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"离开队伍失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/team/disband', methods=['POST'])
def disband_team():
    """解散队伍"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from team_manager import get_team_manager
        team_mgr = get_team_manager()
        result = team_mgr.disband_team(uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'disband_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"解散队伍失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/team/info', methods=['GET'])
def get_team_info():
    """获取队伍信息"""
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from team_manager import get_team_manager
        team_mgr = get_team_manager()
        info = team_mgr.get_team_info(uid)
        return jsonify({'uid': uid, 'team': info})
    except Exception as e:
        error_log(f"获取队伍信息失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 交易系统
# ───────────────────────────────────────────────

@social_bp.route('/social/trade/request', methods=['POST'])
def send_trade_request():
    """发起交易请求"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from trade_manager import get_trade_manager
        trade_mgr = get_trade_manager()
        result = trade_mgr.create_trade(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'request_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"发起交易请求失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/trade/offer', methods=['POST'])
def trade_offer():
    """放置交易物品"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    trade_id = data.get('trade_id', '')
    items = data.get('items', [])

    if not uid or not trade_id:
        return jsonify({'error': {'message': 'uid 和 trade_id 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from trade_manager import get_trade_manager
        trade_mgr = get_trade_manager()
        result = trade_mgr.offer_items(uid, trade_id, items)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'offer_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"放置交易物品失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/trade/confirm', methods=['POST'])
def confirm_trade():
    """确认交易"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    trade_id = data.get('trade_id', '')

    if not uid or not trade_id:
        return jsonify({'error': {'message': 'uid 和 trade_id 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from trade_manager import get_trade_manager
        trade_mgr = get_trade_manager()
        result = trade_mgr.confirm_trade(uid, trade_id)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'confirm_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"确认交易失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/trade/cancel', methods=['POST'])
def cancel_trade():
    """取消交易"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    trade_id = data.get('trade_id', '')

    if not uid or not trade_id:
        return jsonify({'error': {'message': 'uid 和 trade_id 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from trade_manager import get_trade_manager
        trade_mgr = get_trade_manager()
        result = trade_mgr.cancel_trade(uid, trade_id)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'cancel_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"取消交易失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


# ───────────────────────────────────────────────
# 切磋/斗法系统
# ───────────────────────────────────────────────

@social_bp.route('/social/combat/challenge', methods=['POST'])
def send_combat_challenge():
    """发起切磋挑战"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    target_uid = data.get('target_uid', '')

    if not uid or not target_uid:
        return jsonify({'error': {'message': 'uid 和 target_uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from combat_manager import get_combat_manager
        combat_mgr = get_combat_manager()
        result = combat_mgr.create_combat(uid, target_uid)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'challenge_failed'}}), 400

        return jsonify(result), 201
    except Exception as e:
        error_log(f"发起切磋挑战失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/combat/accept', methods=['POST'])
def accept_combat_challenge():
    """接受切磋挑战"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    combat_id = data.get('combat_id', '')

    if not uid or not combat_id:
        return jsonify({'error': {'message': 'uid 和 combat_id 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from combat_manager import get_combat_manager
        combat_mgr = get_combat_manager()
        result = combat_mgr.accept_combat(uid, combat_id)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'accept_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"接受切磋挑战失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/combat/action', methods=['POST'])
def combat_action():
    """战斗行动"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    combat_id = data.get('combat_id', '')
    action = data.get('action', '')

    if not uid or not combat_id or not action:
        return jsonify({'error': {'message': 'uid、combat_id 和 action 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from combat_manager import get_combat_manager
        combat_mgr = get_combat_manager()
        result = combat_mgr.execute_action(uid, combat_id, action)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'action_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"战斗行动失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/combat/flee', methods=['POST'])
def combat_flee():
    """逃跑"""
    data = request.get_json()
    if not data:
        return jsonify({'error': {'message': '请求体不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    uid = data.get('uid', '')
    combat_id = data.get('combat_id', '')

    if not uid or not combat_id:
        return jsonify({'error': {'message': 'uid 和 combat_id 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from combat_manager import get_combat_manager
        combat_mgr = get_combat_manager()
        result = combat_mgr.flee_combat(uid, combat_id)

        if 'error' in result:
            return jsonify({'error': {'message': result['error'], 'type': 'invalid_request_error', 'code': 'flee_failed'}}), 400

        return jsonify(result)
    except Exception as e:
        error_log(f"逃跑失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500


@social_bp.route('/social/combat/info', methods=['GET'])
def get_combat_info():
    """获取战斗状态"""
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({'error': {'message': 'uid 不能为空', 'type': 'invalid_request_error', 'code': 'invalid_request'}}), 400

    try:
        from combat_manager import get_combat_manager
        combat_mgr = get_combat_manager()
        info = combat_mgr.get_combat_info(uid)
        return jsonify({'uid': uid, 'combat': info})
    except Exception as e:
        error_log(f"获取战斗状态失败: {e}")
        return jsonify({'error': {'message': f'服务器内部错误: {str(e)}', 'type': 'internal_server_error', 'code': 'internal_error'}}), 500
