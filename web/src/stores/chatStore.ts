import { create } from 'zustand';
import type { ChatMessage } from '../types';
import { config } from '../config';
import { getOrCreateUserId, getAuthHeaders } from '../lib/user';
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
  hasMoreHistory: boolean;
  isLoadingHistory: boolean;
  earliestTimestamp: number | null;
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
  loadChatHistory: () => Promise<void>;
  loadMoreHistory: () => Promise<void>;
  clearHistory: () => Promise<void>;
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
 * 解析历史记录中的 content，如果 content 是 JSON 字符串则提取 dialog/actions 等字段
 */
function parseHistoryDoc(doc: Record<string, unknown>): ChatMessage {
  const baseMessage: ChatMessage = {
    id: (doc._id as string) || generateId(),
    sender: (doc.sender as 'player' | 'npc' | 'system') || 'system',
    content: (doc.content as string) || '',
    timestamp: (doc.timestamp as number) || Date.now(),
    type: 'normal' as const,
    gameDate: (doc.game_date as string) || undefined,
    gameShichen: (doc.game_shichen as string) || undefined,
    location: (doc.location as string) || undefined,
  };

  // 尝试解析 content 中的 JSON
  if (typeof doc.content === 'string') {
    const trimmed = doc.content.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed.dialog === 'string') {
          baseMessage.content = parsed.dialog;
          if (Array.isArray(parsed.actions)) {
            baseMessage.actions = parsed.actions.filter((a: unknown): a is string => typeof a === 'string');
          }
          baseMessage.parsedJSON = parsed;
          baseMessage.rawJSON = doc.content;
          console.log('[parseHistoryDoc] 解析 JSON 成功，id:', baseMessage.id, 'dialog 长度:', parsed.dialog.length);
        }
      } catch {
        console.warn('[parseHistoryDoc] JSON 解析失败，id:', baseMessage.id, 'content 前50字符:', trimmed.slice(0, 50));
      }
    } else {
      console.log('[parseHistoryDoc] 无需解析，id:', baseMessage.id, 'content 前50字符:', trimmed.slice(0, 50));
    }
  }

  // 如果数据库中已有独立的 actions 字段，也保留
  if (!baseMessage.actions && Array.isArray(doc.actions)) {
    baseMessage.actions = doc.actions as string[];
  }

  return baseMessage;
}

/**
 * 流式调用 /gm/chat 接口，通过 SSE 逐步接收 GM 响应
 */
async function streamGmChat(
  uid: string,
  userInput: string,
  currentArea: string,
  sessionHistory: { role: string; content: string }[],
  signal: AbortSignal,
  onDialogDelta: (content: string) => void,
  onResult: (result: { dialog: string; actions: string[]; player_update: Record<string, unknown>; ui_config: Record<string, unknown> }) => void,
  onError: (message: string) => void,
  onTimeAdvance?: (data: Record<string, unknown>) => void,
  onBusyState?: (data: Record<string, unknown>) => void,
): Promise<void> {
  const response = await fetch(`${config.API_BASE_URL}/gm/chat`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      uid,
      user_input: userInput,
      current_area: currentArea,
      session_history: sessionHistory,
      req_type: 'chat',
      stream: true,
    }),
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const errorMsg = errorData?.error?.message || `HTTP error! status: ${response.status}`;
    throw new Error(errorMsg);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('无法获取响应流');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // 解析 SSE 事件
    const lines = buffer.split('\n');
    // 保留最后一行（可能不完整）
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const dataStr = line.slice(6);
        try {
          const data = JSON.parse(dataStr);

          switch (currentEvent) {
            case 'dialog_delta':
              onDialogDelta(data.content || '');
              break;
            case 'result':
              onResult(data);
              break;
            case 'error':
              onError(data.message || '未知错误');
              break;
            case 'time_advance':
              onTimeAdvance?.(data);
              break;
            case 'busy_state':
              onBusyState?.(data);
              break;
            case 'done':
              // 流结束
              break;
          }
        } catch {
          // 忽略解析错误
        }
        currentEvent = '';
      }
    }
  }
}

/**
 * 处理 GM 响应中的 player_update 和 ui_config，更新 gameStore
 */
export function applyGmResponseToGameStore(
  playerUpdate: Record<string, unknown>,
  uiConfig: Record<string, unknown>,
) {
  const gameStore = useGameStore.getState();

  // 处理 player_update
  if (playerUpdate && Object.keys(playerUpdate).length > 0) {
    const charUpdates: Record<string, unknown> = {};

    if (typeof playerUpdate.name === 'string') charUpdates.name = playerUpdate.name;
    if (typeof playerUpdate.current_location === 'string') charUpdates.currentLocation = playerUpdate.current_location;
    if (typeof playerUpdate.current_status === 'string') charUpdates.currentStatus = playerUpdate.current_status;
    if (typeof playerUpdate.birth_date === 'string') charUpdates.birthDate = playerUpdate.birth_date;
    if (typeof playerUpdate.lifespan === 'string') charUpdates.lifespan = playerUpdate.lifespan;
    if (typeof playerUpdate.clothing === 'string') charUpdates.clothing = playerUpdate.clothing;
    if (Array.isArray(playerUpdate.inventory)) charUpdates.inventory = playerUpdate.inventory;
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

    // 同步更新 world.location
    if (typeof playerUpdate.current_location === 'string') {
      gameStore.updateWorld({ location: playerUpdate.current_location });
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

  // 处理 layout_hint - 仅根据 GM 的明确指示触发布局更新
  // GM 会在角色/世界发生实质性变化时设置 layout_hint，日常对话不会触发
  const layoutHint = uiConfig.layout_hint as string | undefined;
  if (layoutHint && layoutHint !== '') {
    const { generateLayout } = useGameStore.getState();
    if (layoutHint === 'character' || layoutHint === 'both') {
      generateLayout('character');
    }
    if (layoutHint === 'world' || layoutHint === 'both') {
      generateLayout('world');
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
  hasMoreHistory: true,
  isLoadingHistory: false,
  earliestTimestamp: null,

  addMessage: (message) => {
    const id = generateId();
    // 自动附加当前游戏时间和地点
    const gameState = useGameStore.getState();
    const enrichedMessage = {
      ...message,
      gameDate: gameState.world.gameDate || undefined,
      gameShichen: gameState.world.time ? `${gameState.world.time}${gameState.world.timePeriod ? `·${gameState.world.timePeriod}` : ''}` : undefined,
      location: gameState.world.location || undefined,
    };
    set((state) => ({
      messages: [
        ...state.messages,
        {
          ...enrichedMessage,
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
    let outputTokenCount = 0;

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

      await streamGmChat(
        getOrCreateUserId(),
        userInput,
        currentArea,
        sessionHistory,
        abortController.signal,
        // onDialogDelta
        (delta) => {
          outputTokenCount += Math.ceil(delta.length * 0.5);
          const { messages: currentMessages } = get();
          const lastMsg = currentMessages[currentMessages.length - 1];
          if (lastMsg && lastMsg.sender === 'npc') {
            const newContent = lastMsg.content + delta;
            updateLastMessage(newContent);
            set({ streamingContent: newContent });

            const elapsedSeconds = (Date.now() - startTime) / 1000;
            const tokensPerSecond = elapsedSeconds > 0 ? outputTokenCount / elapsedSeconds : 0;
            set((state) => ({
              streamStats: {
                ...state.streamStats,
                outputTokens: outputTokenCount,
                tokensPerSecond: Math.round(tokensPerSecond * 10) / 10,
              },
            }));
          }
        },
        // onResult
        (result) => {
          const actions = Array.isArray(result.actions)
            ? result.actions.filter((a): a is string => typeof a === 'string')
            : [];
          if (actions.length > 0) {
            updateLastMessageActions(actions);
          }

          updateLastMessageParsedJSON(result as unknown as Record<string, unknown>);
          updateLastMessageRawJSON(JSON.stringify(result, null, 2));

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

          applyGmResponseToGameStore(result.player_update || {}, result.ui_config || {});
        },
        // onError
        (message) => {
          console.error('流式响应错误:', message);
          const { messages: currentMessages } = get();
          const lastMsg = currentMessages[currentMessages.length - 1];
          if (lastMsg && lastMsg.sender === 'npc' && !lastMsg.content) {
            updateLastMessage(`错误: ${message}`);
          }
        },
        // onTimeAdvance
        (data) => {
          const gameStore = useGameStore.getState();
          gameStore.handleTimeAdvance(data as unknown as import('../types').TimeAdvanceInfo);
        },
        // onBusyState
        (data) => {
          const gameStore = useGameStore.getState();
          gameStore.handleBusyState(data as unknown as import('../types').BusyState);
        },
      );

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

  loadChatHistory: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    set({ isLoadingHistory: true });

    try {
      const response = await fetch(`${config.API_BASE_URL}/chat/history?uid=${encodeURIComponent(uid)}&limit=10`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('加载聊天历史失败:', response.status);
        set({ isLoadingHistory: false });
        return;
      }

      const data = await response.json();
      const docs = data.messages || [];

      if (docs.length === 0) {
        set({ hasMoreHistory: false, isLoadingHistory: false, earliestTimestamp: null });
        return;
      }

      // 将数据库记录转换为 ChatMessage 格式
      const messages: ChatMessage[] = docs.map(parseHistoryDoc);

      // 调试：输出第一条消息的转换结果
      if (messages.length > 0) {
        const first = messages[0];
        console.log('[ChatHistory] 第一条消息 id:', first.id, 'sender:', first.sender, 'content 前50字符:', first.content?.slice(0, 50), 'rawJSON 是否存在:', !!first.rawJSON);
      }

      // 记录最早的时间戳（用于下次分页加载）
      const earliestTimestamp = docs.length > 0 ? (docs[0].timestamp as number) : null;

      set({
        messages,
        hasMoreHistory: docs.length === 10,
        isLoadingHistory: false,
        earliestTimestamp,
      });
      console.log(`[ChatHistory] 加载了 ${messages.length} 条历史消息`);
    } catch (error) {
      console.error('加载聊天历史失败:', error);
      set({ isLoadingHistory: false });
    }
  },

  loadMoreHistory: async () => {
    const { earliestTimestamp, hasMoreHistory, isLoadingHistory } = get();
    if (!hasMoreHistory || isLoadingHistory || !earliestTimestamp) return;

    const uid = getOrCreateUserId();
    if (!uid) return;

    set({ isLoadingHistory: true });

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/chat/history?uid=${encodeURIComponent(uid)}&limit=10&before_timestamp=${earliestTimestamp}`,
        { headers: getAuthHeaders() }
      );
      if (!response.ok) {
        console.error('加载更多聊天历史失败:', response.status);
        set({ isLoadingHistory: false });
        return;
      }

      const data = await response.json();
      const docs = data.messages || [];

      if (docs.length === 0) {
        set({ hasMoreHistory: false, isLoadingHistory: false });
        return;
      }

      // 将数据库记录转换为 ChatMessage 格式
      const newMessages: ChatMessage[] = docs.map(parseHistoryDoc);

      const newEarliestTimestamp = docs.length > 0 ? (docs[0].timestamp as number) : earliestTimestamp;

      set((state) => ({
        messages: [...newMessages, ...state.messages],
        hasMoreHistory: docs.length === 10,
        isLoadingHistory: false,
        earliestTimestamp: newEarliestTimestamp,
      }));
      console.log(`[ChatHistory] 加载了更多 ${newMessages.length} 条历史消息`);
    } catch (error) {
      console.error('加载更多聊天历史失败:', error);
      set({ isLoadingHistory: false });
    }
  },

  clearHistory: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/chat/history?uid=${encodeURIComponent(uid)}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        set({ messages: [], hasMoreHistory: true, earliestTimestamp: null });
        console.log('[ChatHistory] 聊天历史已清除');
      } else {
        console.error('清除聊天历史失败:', response.status);
      }
    } catch (error) {
      console.error('清除聊天历史失败:', error);
    }
  },

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
    let outputTokenCount = 0;

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

      await streamGmChat(
        getOrCreateUserId(),
        content,
        currentArea,
        sessionHistory,
        abortController.signal,
        // onDialogDelta: 增量更新消息内容
        (delta) => {
          outputTokenCount += Math.ceil(delta.length * 0.5);
          const { messages: currentMessages } = get();
          const lastMsg = currentMessages[currentMessages.length - 1];
          if (lastMsg && lastMsg.sender === 'npc') {
            const newContent = lastMsg.content + delta;
            updateLastMessage(newContent);
            set({ streamingContent: newContent });

            // 更新流式统计
            const elapsedSeconds = (Date.now() - startTime) / 1000;
            const tokensPerSecond = elapsedSeconds > 0 ? outputTokenCount / elapsedSeconds : 0;
            set((state) => ({
              streamStats: {
                ...state.streamStats,
                outputTokens: outputTokenCount,
                tokensPerSecond: Math.round(tokensPerSecond * 10) / 10,
              },
            }));
          }
        },
        // onResult: 收到完整结果
        (result) => {
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
        },
        // onError
        (message) => {
          console.error('流式响应错误:', message);
          const { messages: currentMessages } = get();
          const lastMsg = currentMessages[currentMessages.length - 1];
          if (lastMsg && lastMsg.sender === 'npc' && !lastMsg.content) {
            updateLastMessage(`错误: ${message}`);
          }
        },
        // onTimeAdvance
        (data) => {
          const gameStore = useGameStore.getState();
          gameStore.handleTimeAdvance(data as unknown as import('../types').TimeAdvanceInfo);
        },
        // onBusyState
        (data) => {
          const gameStore = useGameStore.getState();
          gameStore.handleBusyState(data as unknown as import('../types').BusyState);
        },
      );

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
