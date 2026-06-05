import { create } from 'zustand';
import type { ChatMessage } from '../types';
import { config } from '../config';
import { getOrCreateUserId } from '../lib/user';

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
    const { messages, addMessage, updateLastMessage, updateLastMessageActions, updateLastMessageParsedJSON, resetStreamStats, deleteMessage } = get();

    // 找到要重新生成的消息
    const messageIndex = messages.findIndex((m) => m.id === messageId);
    if (messageIndex === -1) return;

    // 获取该消息之前的所有消息（包括用户消息）
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
    let outputTokens = 0;
    let rawContent = '';
    let lastParsedMessage = '';
    let hasParsedJSON = false;

    try {
      // 构建 history_msg：取最近 10 轮对话（排除系统消息），转换为 {role, content} 格式
      const historyMsg = previousMessages
        .filter((m) => m.sender !== 'system')
        .slice(-20) // 最多 20 条消息（10 轮对话）
        .map((m) => ({
          role: m.sender === 'player' ? 'user' : 'assistant',
          content: m.content,
        }));

      // 获取当前位置信息（从 gameStore 或默认值）
      const currentLocation = '青云古域·云溪村'; // TODO: 可从 gameStore 获取

      // 获取最后一条用户消息作为 input_text
      const lastUserMessage = previousMessages
        .filter((m) => m.sender === 'player')
        .pop();
      const inputText = lastUserMessage ? lastUserMessage.content : '';

      const response = await fetch(`${config.API_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': getOrCreateUserId(),
        },
        body: JSON.stringify({
          uid: getOrCreateUserId(),
          input_text: inputText,
          current_location: currentLocation,
          req_type: 'chat',
          history_msg: historyMsg,
          stream: true,
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('无法获取响应流');
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        if (abortController.signal.aborted) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            try {
              const parsed = JSON.parse(data);
              const delta = parsed.choices?.[0]?.delta?.content;
              if (delta) {
                outputTokens += 1;
                rawContent += delta;

                const elapsedSeconds = (Date.now() - startTime) / 1000;
                const tokensPerSecond = elapsedSeconds > 0 ? outputTokens / elapsedSeconds : 0;

                set((state) => ({
                  streamStats: {
                    ...state.streamStats,
                    outputTokens,
                    tokensPerSecond: Math.round(tokensPerSecond * 10) / 10,
                  },
                }));

                // 尝试解析 JSON，提取 message 字段进行流式展示
                let displayContent = rawContent;
                try {
                  const jsonData = JSON.parse(rawContent);
                  if (jsonData && typeof jsonData === 'object') {
                    hasParsedJSON = true;
                    // 提取 message 字段用于流式展示
                    if (typeof jsonData.message === 'string') {
                      displayContent = jsonData.message;
                      lastParsedMessage = jsonData.message;
                    }
                    // 提取 actions 字段
                    if (Array.isArray(jsonData.actions)) {
                      const actions = jsonData.actions.filter((a: unknown) => typeof a === 'string') as string[];
                      updateLastMessageActions(actions);
                    }
                    // 保存完整解析的 JSON
                    updateLastMessageParsedJSON(jsonData as Record<string, unknown>);
                    // 提取 location 和 time
                    const updates: Partial<ChatState> = {};
                    if (typeof jsonData.location === 'string') {
                      updates.lastLocation = jsonData.location;
                    }
                    if (typeof jsonData.time === 'string') {
                      updates.lastTime = jsonData.time;
                    }
                    if (updates.lastLocation || updates.lastTime) {
                      set(updates);
                    }
                  }
                } catch {
                  // JSON 尚未完整，如果之前解析过 message，则继续展示上次解析的 message
                  if (hasParsedJSON && lastParsedMessage) {
                    displayContent = lastParsedMessage;
                  }
                }

                updateLastMessage(displayContent);
                set({ streamingContent: rawContent });
              }
            } catch {
              // 忽略解析错误的行
            }
          }
        }
      }
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
    const { messages, addMessage, updateLastMessage, updateLastMessageActions, updateLastMessageParsedJSON, resetStreamStats } = get();

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

    // 先添加一个空的AI消息，用于流式更新
    addMessage({
      sender: 'npc',
      senderName: '云溪村长',
      senderAvatar: '👴',
      content: '',
      type: 'normal',
    });

    // 计算上下文 token 数（简单估算：每个字符约 0.5 个 token）
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
    let outputTokens = 0;
    let rawContent = '';
    let lastParsedMessage = '';
    let hasParsedJSON = false;

    try {
      // 构建 history_msg：取最近 10 轮对话（排除系统消息），转换为 {role, content} 格式
      const historyMsg = messages
        .filter((m) => m.sender !== 'system')
        .slice(-20) // 最多 20 条消息（10 轮对话）
        .map((m) => ({
          role: m.sender === 'player' ? 'user' : 'assistant',
          content: m.content,
        }));

      // 获取当前位置信息（从 gameStore 或默认值）
      const currentLocation = '青云古域·云溪村'; // TODO: 可从 gameStore 获取

      const response = await fetch(`${config.API_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': getOrCreateUserId(),
        },
        body: JSON.stringify({
          uid: getOrCreateUserId(),
          input_text: content,
          current_location: currentLocation,
          req_type: 'chat',
          history_msg: historyMsg,
          stream: true,
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('无法获取响应流');
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // 检查是否已中止
        if (abortController.signal.aborted) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            try {
              const parsed = JSON.parse(data);
              const delta = parsed.choices?.[0]?.delta?.content;
              if (delta) {
                outputTokens += 1;
                rawContent += delta;

                // 计算生成速度
                const elapsedSeconds = (Date.now() - startTime) / 1000;
                const tokensPerSecond = elapsedSeconds > 0 ? outputTokens / elapsedSeconds : 0;

                // 更新统计信息
                set((state) => ({
                  streamStats: {
                    ...state.streamStats,
                    outputTokens,
                    tokensPerSecond: Math.round(tokensPerSecond * 10) / 10,
                  },
                }));

                // 尝试解析 JSON，提取 message 字段进行流式展示
                let displayContent = rawContent;
                try {
                  const jsonData = JSON.parse(rawContent);
                  if (jsonData && typeof jsonData === 'object') {
                    hasParsedJSON = true;
                    // 提取 message 字段用于流式展示
                    if (typeof jsonData.message === 'string') {
                      displayContent = jsonData.message;
                      lastParsedMessage = jsonData.message;
                    }
                    // 提取 actions 字段
                    if (Array.isArray(jsonData.actions)) {
                      const actions = jsonData.actions.filter((a: unknown) => typeof a === 'string') as string[];
                      updateLastMessageActions(actions);
                    }
                    // 保存完整解析的 JSON
                    updateLastMessageParsedJSON(jsonData as Record<string, unknown>);
                    // 提取 location 和 time
                    const updates: Partial<ChatState> = {};
                    if (typeof jsonData.location === 'string') {
                      updates.lastLocation = jsonData.location;
                    }
                    if (typeof jsonData.time === 'string') {
                      updates.lastTime = jsonData.time;
                    }
                    if (updates.lastLocation || updates.lastTime) {
                      set(updates);
                    }
                  }
                } catch {
                  // JSON 尚未完整，如果之前解析过 message，则继续展示上次解析的 message
                  if (hasParsedJSON && lastParsedMessage) {
                    displayContent = lastParsedMessage;
                  }
                }

                updateLastMessage(displayContent);
                set({ streamingContent: rawContent });
              }
            } catch {
              // 忽略解析错误的行
            }
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // 用户主动停止，不显示错误
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
