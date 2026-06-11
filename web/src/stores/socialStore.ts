import { create } from 'zustand';
import type { ChatContact, PrivateMessage, AreaMessage } from '../types';
import { config } from '../config';
import { getOrCreateUserId, getAuthHeaders } from '../lib/user';

interface SocialRequest {
  type: 'friend' | 'friend_request' | 'team' | 'team_invite' | 'trade' | 'combat';
  from_uid: string;
  from_name: string;
  [key: string]: unknown;
}

interface SocialState {
  contacts: ChatContact[];
  privateMessages: PrivateMessage[];
  areaMessages: AreaMessage[];
  selectedContactUid: string | null;
  socialRequests: SocialRequest[];
  isSocialPanelOpen: boolean;
  activeTab: 'contacts' | 'area' | 'friends' | 'team';

  // Actions
  sendPrivateMessage: (toUid: string, content: string) => Promise<void>;
  loadPrivateMessages: (peerUid: string) => Promise<void>;
  sendAreaMessage: (content: string) => Promise<void>;
  loadAreaMessages: (location: string) => Promise<void>;
  loadContacts: () => Promise<void>;
  selectContact: (uid: string | null) => void;
  receivePrivateMessage: (data: Record<string, unknown>) => void;
  receiveAreaMessage: (data: Record<string, unknown>) => void;
  receiveSocialRequest: (data: Record<string, unknown>) => void;
  setSocialPanelOpen: (open: boolean) => void;
  setActiveTab: (tab: 'contacts' | 'area' | 'friends' | 'team') => void;
  clearSocialRequests: () => void;

  // Friend actions
  sendFriendRequest: (targetUid: string) => Promise<void>;
  acceptFriendRequest: (fromUid: string) => Promise<void>;
  rejectFriendRequest: (fromUid: string) => Promise<void>;
  deleteFriend: (targetUid: string) => Promise<void>;
  loadFriends: () => Promise<void>;
  loadFriendRequests: () => Promise<void>;
  friends: ChatContact[];
  friendRequests: SocialRequest[];

  // Team actions
  createTeam: () => Promise<void>;
  inviteTeamMember: (targetUid: string) => Promise<void>;
  acceptTeamInvite: (teamId: string) => Promise<void>;
  leaveTeam: () => Promise<void>;
  disbandTeam: () => Promise<void>;
  loadTeamInfo: () => Promise<void>;
  teamInfo: Record<string, unknown> | null;
}

export const useSocialStore = create<SocialState>((set, get) => ({
  contacts: [],
  privateMessages: [],
  areaMessages: [],
  selectedContactUid: null,
  socialRequests: [],
  isSocialPanelOpen: false,
  activeTab: 'contacts',
  friends: [],
  friendRequests: [],
  teamInfo: null,

  sendPrivateMessage: async (toUid, content) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/social/message/send`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, to_uid: toUid, content }),
      });
      if (!response.ok) {
        console.error('[Social] 发送私聊消息失败:', response.status);
        return;
      }

      // 刷新聊天记录
      const { loadPrivateMessages, selectedContactUid } = get();
      if (selectedContactUid === toUid) {
        loadPrivateMessages(toUid);
      }
    } catch (error) {
      console.error('[Social] 发送私聊消息失败:', error);
    }
  },

  loadPrivateMessages: async (peerUid) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/social/message/history?uid=${encodeURIComponent(uid)}&peer_uid=${encodeURIComponent(peerUid)}`,
        { headers: getAuthHeaders() }
      );
      if (!response.ok) return;

      const data = await response.json();
      if (Array.isArray(data.messages)) {
        const messages: PrivateMessage[] = data.messages.map((m: Record<string, unknown>) => ({
          id: (m._id as string) || '',
          fromUid: (m.from_uid as string) || '',
          fromName: (m.from_name as string) || '',
          toUid: (m.to_uid as string) || '',
          toName: (m.to_name as string) || '',
          content: (m.content as string) || '',
          timestamp: (m.timestamp as number) || 0,
          read: (m.read as boolean) || false,
        }));
        set({ privateMessages: messages.reverse() });
      }
    } catch (error) {
      console.error('[Social] 加载私聊记录失败:', error);
    }
  },

  sendAreaMessage: async (content) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/social/area-message`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, content }),
      });
      if (!response.ok) {
        console.error('[Social] 发送区域消息失败:', response.status);
      }
    } catch (error) {
      console.error('[Social] 发送区域消息失败:', error);
    }
  },

  loadAreaMessages: async (location) => {
    try {
      const response = await fetch(
        `${config.API_BASE_URL}/social/area-messages?location=${encodeURIComponent(location)}&limit=50`,
        { headers: getAuthHeaders() }
      );
      if (!response.ok) return;

      const data = await response.json();
      if (Array.isArray(data.messages)) {
        const messages: AreaMessage[] = data.messages.map((m: Record<string, unknown>) => ({
          id: (m._id as string) || '',
          fromUid: (m.from_uid as string) || '',
          fromName: (m.from_name as string) || '',
          location: (m.location as string) || '',
          content: (m.content as string) || '',
          timestamp: (m.timestamp as number) || 0,
        }));
        set({ areaMessages: messages.reverse() });
      }
    } catch (error) {
      console.error('[Social] 加载区域消息失败:', error);
    }
  },

  loadContacts: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/social/contacts?uid=${encodeURIComponent(uid)}`,
        { headers: getAuthHeaders() }
      );
      if (!response.ok) return;

      const data = await response.json();
      if (Array.isArray(data.contacts)) {
        set({ contacts: data.contacts });
      }
    } catch (error) {
      console.error('[Social] 加载联系人失败:', error);
    }
  },

  selectContact: (uid) => {
    set({ selectedContactUid: uid });
    if (uid) {
      get().loadPrivateMessages(uid);
    }
  },

  receivePrivateMessage: (data) => {
    const msg: PrivateMessage = {
      id: (data.msg_id as string) || '',
      fromUid: (data.from_uid as string) || '',
      fromName: (data.from_name as string) || '',
      toUid: (data.to_uid as string) || '',
      toName: (data.to_name as string) || '',
      content: (data.content as string) || '',
      timestamp: (data.timestamp as number) || 0,
      read: false,
    };

    set((state) => {
      // 如果正在查看该联系人的聊天，直接添加
      if (state.selectedContactUid === msg.fromUid) {
        return { privateMessages: [...state.privateMessages, msg] };
      }
      return state;
    });

    // 刷新联系人列表
    get().loadContacts();
  },

  receiveAreaMessage: (data) => {
    const msg: AreaMessage = {
      id: (data.msg_id as string) || '',
      fromUid: (data.from_uid as string) || '',
      fromName: (data.from_name as string) || '',
      location: (data.location as string) || '',
      content: (data.content as string) || '',
      timestamp: (data.timestamp as number) || 0,
    };

    set((state) => ({
      areaMessages: [...state.areaMessages, msg],
    }));
  },

  receiveSocialRequest: (data) => {
    const req: SocialRequest = {
      type: (data.type as SocialRequest['type']) || 'friend',
      from_uid: (data.from_uid as string) || '',
      from_name: (data.from_name as string) || '',
      ...data,
    };

    set((state) => ({
      socialRequests: [...state.socialRequests, req],
    }));
  },

  setSocialPanelOpen: (open) => set({ isSocialPanelOpen: open }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  clearSocialRequests: () => set({ socialRequests: [] }),

  // ───────────────────────────────────────────────
  // 好友操作
  // ───────────────────────────────────────────────

  sendFriendRequest: async (targetUid) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/friend/request`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, target_uid: targetUid }),
      });
    } catch (error) {
      console.error('[Social] 发送好友申请失败:', error);
    }
  },

  acceptFriendRequest: async (fromUid) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/friend/accept`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, from_uid: fromUid }),
      });
      get().loadFriends();
      get().loadFriendRequests();
    } catch (error) {
      console.error('[Social] 接受好友申请失败:', error);
    }
  },

  rejectFriendRequest: async (fromUid) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/friend/reject`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, from_uid: fromUid }),
      });
      get().loadFriendRequests();
    } catch (error) {
      console.error('[Social] 拒绝好友申请失败:', error);
    }
  },

  deleteFriend: async (targetUid) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/friend/${encodeURIComponent(targetUid)}?uid=${encodeURIComponent(uid)}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      get().loadFriends();
    } catch (error) {
      console.error('[Social] 删除好友失败:', error);
    }
  },

  loadFriends: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/social/friends?uid=${encodeURIComponent(uid)}`,
        { headers: getAuthHeaders() }
      );
      if (!response.ok) return;

      const data = await response.json();
      if (Array.isArray(data.friends)) {
        set({ friends: data.friends });
      }
    } catch (error) {
      console.error('[Social] 加载好友列表失败:', error);
    }
  },

  loadFriendRequests: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/social/friend/requests?uid=${encodeURIComponent(uid)}`,
        { headers: getAuthHeaders() }
      );
      if (!response.ok) return;

      const data = await response.json();
      if (Array.isArray(data.requests)) {
        set({ friendRequests: data.requests });
      }
    } catch (error) {
      console.error('[Social] 加载好友申请失败:', error);
    }
  },

  // ───────────────────────────────────────────────
  // 组队操作
  // ───────────────────────────────────────────────

  createTeam: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/team/create`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid }),
      });
      get().loadTeamInfo();
    } catch (error) {
      console.error('[Social] 创建队伍失败:', error);
    }
  },

  inviteTeamMember: async (targetUid) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/team/invite`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, target_uid: targetUid }),
      });
    } catch (error) {
      console.error('[Social] 邀请入队失败:', error);
    }
  },

  acceptTeamInvite: async (teamId) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/team/accept`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, team_id: teamId }),
      });
      get().loadTeamInfo();
    } catch (error) {
      console.error('[Social] 接受入队邀请失败:', error);
    }
  },

  leaveTeam: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/team/leave`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid }),
      });
      get().loadTeamInfo();
    } catch (error) {
      console.error('[Social] 离开队伍失败:', error);
    }
  },

  disbandTeam: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      await fetch(`${config.API_BASE_URL}/social/team/disband`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid }),
      });
      set({ teamInfo: null });
    } catch (error) {
      console.error('[Social] 解散队伍失败:', error);
    }
  },

  loadTeamInfo: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/social/team/info?uid=${encodeURIComponent(uid)}`,
        { headers: getAuthHeaders() }
      );
      if (!response.ok) return;

      const data = await response.json();
      set({ teamInfo: data.team || null });
    } catch (error) {
      console.error('[Social] 加载队伍信息失败:', error);
    }
  },
}));
