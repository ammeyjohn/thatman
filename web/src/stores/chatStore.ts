import { create } from 'zustand';
import type { ChatMessage } from '../types';
import { config } from '../config';
import { getOrCreateUserId } from '../lib/user';
import { useGameStore } from './gameStore';

let messageIdCounter = 0;
const generateId = () => {
  messageIdCounter += 1;
  return `${Date.now()}-${messageIdCounter}`;
};

export interface StreamStats {
  contextTokens: number;
  contextMax: number;
  outputTokens: number;
  outputMax: number | null;
  tokensPerSecond: number;
}

interface ChatState {
  messages: ChatMessage[];
  inputValue: string;
  isLoading: boolean;
  streamingContent: string;
  streamStats: StreamStats;
  abortController: AbortController | null;
  lastLocation: string | null;
  lastTime: string | null;
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => string;
  updateLastMessage: (content: string) => void;
  updateLastMessageOptions: (options: string[]) => void;
  updateLastMessageActions: (actions: string[]) => void;
  updateLastMessageParsedJSON: (parsedJSON: Record<string, unknown>) => void;
  updateLastMessageRawJSON: (rawJSON: string) => void;
  setInputValue: (value: string) => void;
  setStreamingContent: (content: string) => void;
  clearMessages: () => void;
  sendMessage: (content: string) => Promise<void>;
  stopGeneration: () => void;
  resetStreamStats: () => void;
  deleteMessage: (messageId: string) => void;
  editMessage: (messageId: string, newContent: string) => void;
  regenerateMessage: (messageId: string) => Promise<void>;
}

const initialMessages: ChatMessage[] = [];

const initialStreamStats: StreamStats = {
  contextTokens: 0,
  contextMax: 262144,
  outputTokens: 0,
  outputMax: null,
  tokensPerSecond: 0,
};

/**
 * 调用 /gm/chat 接口，处理 GM 响应
 */
async function callGmChat(
  uid: string,
  userInput: string,
  currentArea: string,
  sessionHistory: { role: string; content: string }[],
  signal?: AbortSignal,
): Promise<{ dialog: string; actions: string[]; player_update: Record<string, unknown>; ui_config: Record<string, unknown> }> {
  const response = await fetch(`${config.API_BASE_URL}/gm/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      uid,
      user_input: userInput,
      current_area: currentArea,
      session_history: sessionHistory,
      req_type: 'chat',
    }),
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const errorMsg = errorData?.error?.message || `HTTP error! status: ${response.status}`;
    throw new Error(errorMsg);
  }

  return response.json();
}

/**
 * 处理 GM 响应中的 player_update 和 ui_config，更新 gameStore
 */
function applyGmResponseToGameStore(
  playerUpdate: Record<string, unknown>,
  uiConfig: Record<string, unknown>,
) {
  const gameStore = useGameStore.getState();

  // 处理 player_update
  if (playerUpdate && Object.keys(playerUpdate).length > 0) {
    const charUpdates: Record<string, unknown> = {};

    if (typeof playerUpdate.name === 'string') charUpdates.name = playerUpdate.name;
    if (typeof playerUpdate.realm === 'string') charUpdates.realm = playerUpdate.realm;
    if (typeof playerUpdate.realm_stage === 'string') charUpdates.realmStage = playerUpdate.realm_stage;
    if (typeof playerUpdate.level === 'number') charUpdates.level = playerUpdate.level;
    if (typeof playerUpdate.health === 'number') charUpdates.health = playerUpdate.health;
    if (typeof playerUpdate.max_health === 'number') charUpdates.maxHealth = playerUpdate.max_health;
    if (typeof playerUpdate.mana === 'number') charUpdates.mana = playerUpdate.mana;
    if (typeof playerUpdate.max_mana === 'number') charUpdates.maxMana = playerUpdate.max_mana;
    if (typeof playerUpdate.spirit === 'number') charUpdates.spirit = playerUpdate.spirit;
    if (typeof playerUpdate.max_spirit === 'number') charUpdates.maxSpirit = playerUpdate.max_spirit;
    if (Array.isArray(playerUpdate.equipment)) charUpdates.equipment = playerUpdate.equipment;

    if (Object.keys(charUpdates).length > 0) {
      gameStore.updateCharacter(charUpdates);
    }
  }

  // 处理 ui_config
  if (uiConfig && Object.keys(uiConfig).length > 0) {
    const worldUpdates: Record<string, unknown> = {};

    if (typeof uiConfig.location === 'string') worldUpdates.location = uiConfig.location;
    if (typeof uiConfig.time === 'string') worldUpdates.time = uiConfig.time;
    if (typeof uiConfig.weather === 'string') worldUpdates.weather = uiConfig.weather;

    if (Object.keys(worldUpdates).length > 0) {
      gameStore.updateWorld(worldUpdates);
    }
  }
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: initialMessages,
  inputValue: '',
  isLoading: false,
  streamingContent: '',
  streamStats: { ...initialStreamStats },
  abortController: null,
  lastLocation: null,
  lastTime: null,

  addMessage: (message) => {
    const id = generateId();
    set((state) => ({
      messages: [
        ...state.messages,
        {
          ...message,
          id,
          timestamp: Date.now(),
        },
      ],
    }));
    return id;
  },

  updateLastMessage: (content) =>
    set((state) => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      if (lastMessage && lastMessage.sender === 'npc') {
        lastMessage.content = content;
      }
      return { messages };
    }),

  updateLastMessageOptions: (options) =>
    set((state) => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      if (lastMessage && lastMessage.sender === 'npc') {
        lastMessage.options = options;
      }
      return { messages };
    }),

  updateLastMessageActions: (actions) =>
    set((state) => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      if (lastMessage && lastMessage.sender === 'npc') {
        lastMessage.actions = actions;
      }
      return { messages };
    }),

  updateLastMessageParsedJSON: (parsedJSON) =>
    set((state) => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      if (lastMessage && lastMessage.sender === 'npc') {
        lastMessage.parsedJSON = parsedJSON;
      }
      return { messages };
    }),

  updateLastMessageRawJSON: (rawJSON) =>
    set((state) => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      if (lastMessage && lastMessage.sender === 'npc') {
        lastMessage.rawJSON = rawJSON;
      }
      return { messages };
    }),

  setInputValue: (value) => set({ inputValue: value }),

  setStreamingContent: (content) => set({ streamingContent: content }),

  clearMessages: () => set({ messages: [] }),

  deleteMessage: (messageId: string) =>
    set((state) => {
      const messageIndex = state.messages.findIndex((m) => m.id === messageId);
      if (messageIndex === -1) return { messages: state.messages };

      const message = state.messages[messageIndex];
      const messagesToDelete = [messageId];

      // 如果删除的是用户消息，同时删除对应的 AI 回复（下一条消息）
      if (message.sender === 'player') {
        const nextMessage = state.messages[messageIndex + 1];
        if (nextMessage && nextMessage.sender === 'npc') {
          messagesToDelete.push(nextMessage.id);
        }
      }

      return {
        messages: state.messages.filter((m) => !messagesToDelete.includes(m.id)),
      };
    }),

  editMessage: (messageId: string, newContent: string) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId ? { ...m, content: newContent } : m
      ),
    })),

  regenerateMessage: async (messageId: string) => {
    const { messages, addMessage, updateLastMessage, updateLastMessageActions, updateLastMessageParsedJSON, updateLastMessageRawJSON, resetStreamStats, deleteMessage } = get();

    // 找到要重新生成的消息
    const messageIndex = messages.findIndex((m) => m.id === messageId);
    if (messageIndex === -1) return;

    // 获取该消息之前的所有消息
    const previousMessages = messages.slice(0, messageIndex);

    // 删除当前AI消息
    deleteMessage(messageId);

    // 重置统计信息
    resetStreamStats();

    // 创建 AbortController
    const abortController = new AbortController();
    set({ isLoading: true, streamingContent: '', abortController });

    // 添加新的空AI消息
    addMessage({
      sender: 'npc',
      senderName: '云溪村长',
      senderAvatar: '👴',
      content: '',
      type: 'normal',
    });

    // 计算上下文 token 数
    const contextText = previousMessages
      .filter((m) => m.sender !== 'system')
      .map((m) => m.content)
      .join('');
    const contextTokens = Math.ceil(contextText.length * 0.5);

    set((state) => ({
      streamStats: {
        ...state.streamStats,
        contextTokens,
      },
    }));

    const startTime = Date.now();

    try {
      // 构建 session_history：取最近 10 轮对话（排除系统消息）
      const sessionHistory = previousMessages
        .filter((m) => m.sender !== 'system')
        .slice(-20)
        .map((m) => ({
          role: m.sender === 'player' ? 'user' : 'assistant',
          content: m.content,
        }));

      // 获取当前位置信息
      const currentArea = useGameStore.getState().world.location;

      // 获取最后一条用户消息作为 user_input
      const lastUserMessage = previousMessages
        .filter((m) => m.sender === 'player')
        .pop();
      const userInput = lastUserMessage ? lastUserMessage.content : '';

      const result = await callGmChat(
        getOrCreateUserId(),
        userInput,
        currentArea,
        sessionHistory,
        abortController.signal,
      );

      const outputTokens = Math.ceil(result.dialog.length * 0.5);
      const elapsedSeconds = (Date.now() - startTime) / 1000;
      const tokensPerSecond = elapsedSeconds > 0 ? outputTokens / elapsedSeconds : 0;

      set((state) => ({
        streamStats: {
          ...state.streamStats,
          outputTokens,
          tokensPerSecond: Math.round(tokensPerSecond * 10) / 10,
        },
      }));

      // 更新消息内容
      updateLastMessage(result.dialog);
      set({ streamingContent: result.dialog });

      // 提取 actions
      const actions = Array.isArray(result.actions)
        ? result.actions.filter((a): a is string => typeof a === 'string')
        : [];
      if (actions.length > 0) {
        updateLastMessageActions(actions);
      }

      // 保存解析后的 JSON
      updateLastMessageParsedJSON(result as unknown as Record<string, unknown>);
      updateLastMessageRawJSON(JSON.stringify(result, null, 2));

      // 更新 location 和 time
      const uiConfig = result.ui_config || {};
      const updates: Partial<ChatState> = {};
      if (typeof uiConfig.location === 'string') {
        updates.lastLocation = uiConfig.location;
      }
      if (typeof uiConfig.time === 'string') {
        updates.lastTime = uiConfig.time;
      }
      if (updates.lastLocation || updates.lastTime) {
        set(updates);
      }

      // 更新 gameStore
      applyGmResponseToGameStore(result.player_update || {}, result.ui_config || {});

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('生成已停止');
      } else {
        console.error('重新生成失败:', error);
        updateLastMessage(`重新生成失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
    } finally {
      set({ isLoading: false, streamingContent: '', abortController: null });
    }
  },

  resetStreamStats: () => set({ streamStats: { ...initialStreamStats } }),

  stopGeneration: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ abortController: null, isLoading: false });
    }
  },

  sendMessage: async (content: string) => {
    const { messages, addMessage, updateLastMessage, updateLastMessageActions, updateLastMessageParsedJSON, updateLastMessageRawJSON, resetStreamStats } = get();

    // 添加用户消息
    addMessage({
      sender: 'player',
      content: content,
      type: 'normal',
    });

    // 重置统计信息
    resetStreamStats();

    // 创建 AbortController
    const abortController = new AbortController();
    set({ isLoading: true, streamingContent: '', abortController });

    // 先添加一个空的AI消息，用于更新
    addMessage({
      sender: 'npc',
      senderName: '云溪村长',
      senderAvatar: '👴',
      content: '',
      type: 'normal',
    });

    // 计算上下文 token 数
    const contextText = messages
      .filter((m) => m.sender !== 'system')
      .map((m) => m.content)
      .join('') + content;
    const contextTokens = Math.ceil(contextText.length * 0.5);

    set((state) => ({
      streamStats: {
        ...state.streamStats,
        contextTokens,
      },
    }));

    const startTime = Date.now();

    try {
      // 构建 session_history：取最近 10 轮对话（排除系统消息）
      const sessionHistory = messages
        .filter((m) => m.sender !== 'system')
        .slice(-20)
        .map((m) => ({
          role: m.sender === 'player' ? 'user' : 'assistant',
          content: m.content,
        }));

      // 获取当前位置信息
      const currentArea = useGameStore.getState().world.location;

      const result = await callGmChat(
        getOrCreateUserId(),
        content,
        currentArea,
        sessionHistory,
        abortController.signal,
      );

      const outputTokens = Math.ceil(result.dialog.length * 0.5);
      const elapsedSeconds = (Date.now() - startTime) / 1000;
      const tokensPerSecond = elapsedSeconds > 0 ? outputTokens / elapsedSeconds : 0;

      set((state) => ({
        streamStats: {
          ...state.streamStats,
          outputTokens,
          tokensPerSecond: Math.round(tokensPerSecond * 10) / 10,
        },
      }));

      // 更新消息内容
      updateLastMessage(result.dialog);
      set({ streamingContent: result.dialog });

      // 提取 actions
      const actions = Array.isArray(result.actions)
        ? result.actions.filter((a): a is string => typeof a === 'string')
        : [];
      if (actions.length > 0) {
        updateLastMessageActions(actions);
      }

      // 保存解析后的 JSON
      updateLastMessageParsedJSON(result as unknown as Record<string, unknown>);
      updateLastMessageRawJSON(JSON.stringify(result, null, 2));

      // 更新 location 和 time
      const uiConfig = result.ui_config || {};
      const updates: Partial<ChatState> = {};
      if (typeof uiConfig.location === 'string') {
        updates.lastLocation = uiConfig.location;
      }
      if (typeof uiConfig.time === 'string') {
        updates.lastTime = uiConfig.time;
      }
      if (updates.lastLocation || updates.lastTime) {
        set(updates);
      }

      // 更新 gameStore
      applyGmResponseToGameStore(result.player_update || {}, result.ui_config || {});

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('生成已停止');
      } else {
        console.error('发送消息失败:', error);
        updateLastMessage(`发送失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
    } finally {
      set({ isLoading: false, streamingContent: '', abortController: null });
    }
  },
}));
