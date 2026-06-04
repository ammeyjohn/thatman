import { create } from 'zustand';
import type { ChatMessage, StreamParseState, WorldState } from '../types';
import { config } from '../config';
import { useGameStore } from './gameStore';
import { getOrCreateUserId } from '../lib/user';

let messageIdCounter = 0;
const generateId = () => {
  messageIdCounter += 1;
  return `${Date.now()}-${messageIdCounter}`;
};

// 流式JSON解析器 - 支持增量解析JSON
class StreamingJSONParser {
  private buffer = '';
  private state: StreamParseState = {
    story: '',
    options: [],
    hint: '',
    panel: ''
  };
  private onUpdate: (state: StreamParseState) => void;

  constructor(onUpdate: (state: StreamParseState) => void) {
    this.onUpdate = onUpdate;
  }

  // 提取JSON中指定键的值（支持嵌套键如 "scene_info.location"）
  private extractValue(jsonStr: string, keyPath: string): string | null {
    const keys = keyPath.split('.');
    let currentStr = jsonStr;

    for (let i = 0; i < keys.length; i++) {
      const key = keys[i];
      const isLast = i === keys.length - 1;

      if (isLast) {
        // 匹配 "key": "value" 或 "key":"value" 格式
        const pattern = new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`, 'i');
        const match = currentStr.match(pattern);
        if (match) {
          return match[1];
        }
        // 匹配不完整的情况，尝试提取部分值
        const partialPattern = new RegExp(`"${key}"\\s*:\\s*"([^"]*)$`, 'i');
        const partialMatch = currentStr.match(partialPattern);
        if (partialMatch) {
          return partialMatch[1];
        }
      } else {
        // 匹配嵌套对象
        const pattern = new RegExp(`"${key}"\\s*:\\s*\\{([^}]*)\\}`, 'i');
        const match = currentStr.match(pattern);
        if (match) {
          currentStr = '{' + match[1] + '}';
        } else {
          // 尝试匹配不完整的嵌套对象
          const partialPattern = new RegExp(`"${key}"\\s*:\\s*\\{([^}]*)$`, 'i');
          const partialMatch = currentStr.match(partialPattern);
          if (partialMatch) {
            currentStr = '{' + partialMatch[1];
          }
        }
      }
    }
    return null;
  }

  // 提取 markdown 内容（去除 ```markdown 和 ``` 标记，以及特殊字符）
  private extractMarkdown(content: string): string {
    // 匹配 ```markdown\n?...\n?``` 或 ```...\n?``` 格式
    const markdownPattern = /```(?:markdown)?\n?([\s\S]*?)(?:\n?```|$)/i;
    const match = content.match(markdownPattern);
    let extractedContent = content;
    if (match) {
      extractedContent = match[1];
    }
    // 去除换行符、回车符等特殊字符
    return extractedContent
      .replace(/\\n/g, '\n')  // 将转义的 \n 转换为实际换行
      .replace(/\\r/g, '')    // 去除 \r
      .replace(/\\t/g, '\t')  // 将转义的 \t 转换为实际制表符
      .replace(/\\"/g, '"')   // 将转义的 \" 转换为实际引号
      .replace(/\\\\/g, '\\') // 将转义的 \\ 转换为实际反斜杠
      .trim();
  }

  // 解析chunk并更新状态
  parse(chunk: string): void {
    this.buffer += chunk;

    // 尝试提取 story
    const story = this.extractValue(this.buffer, 'story');
    if (story !== null) {
      // 提取 markdown 内容（去除代码块标记）
      const markdownContent = this.extractMarkdown(story);
      if (markdownContent !== this.state.story) {
        this.state.story = markdownContent;
      }
    }

    // 尝试提取 scene_info.location
    const location = this.extractValue(this.buffer, 'scene_info.location');
    if (location !== null) {
      if (!this.state.scene_info) {
        this.state.scene_info = {};
      }
      if (location !== this.state.scene_info.location) {
        this.state.scene_info.location = location;
      }
    }

    // 尝试提取 scene_info.time
    const time = this.extractValue(this.buffer, 'scene_info.time');
    if (time !== null) {
      if (!this.state.scene_info) {
        this.state.scene_info = {};
      }
      if (time !== this.state.scene_info.time) {
        this.state.scene_info.time = time;
      }
    }

    // 尝试提取 scene_info.env_effect
    const envEffect = this.extractValue(this.buffer, 'scene_info.env_effect');
    if (envEffect !== null) {
      if (!this.state.scene_info) {
        this.state.scene_info = {};
      }
      if (envEffect !== this.state.scene_info.env_effect) {
        this.state.scene_info.env_effect = envEffect;
      }
    }

    // 尝试提取 hint
    const hint = this.extractValue(this.buffer, 'hint');
    if (hint !== null && hint !== this.state.hint) {
      this.state.hint = hint;
    }

    // 尝试提取 panel
    const panel = this.extractValue(this.buffer, 'panel');
    if (panel !== null && panel !== this.state.panel) {
      this.state.panel = panel;
    }

    // 尝试提取 options 数组
    const options = this.extractArray(this.buffer, 'options');
    if (options !== null) {
      this.state.options = options;
    }

    // 触发更新回调
    this.onUpdate({ ...this.state });
  }

  // 提取JSON中的数组
  private extractArray(jsonStr: string, key: string): string[] | null {
    // 匹配 "key": ["value1", "value2", ...] 格式
    const pattern = new RegExp(`"${key}"\\s*:\\s*\\[([^\\]]*)\\]`, 'i');
    const match = jsonStr.match(pattern);
    if (match) {
      // 解析数组内容
      const arrayContent = match[1];
      // 提取所有字符串值
      const stringPattern = /"([^"]*)"/g;
      const results: string[] = [];
      let stringMatch;
      while ((stringMatch = stringPattern.exec(arrayContent)) !== null) {
        results.push(stringMatch[1]);
      }
      return results;
    }
    return null;
  }

  // 获取当前完整状态
  getState(): StreamParseState {
    return { ...this.state };
  }

  // 重置解析器
  reset(): void {
    this.buffer = '';
    this.state = {
      story: '',
      options: [],
      hint: '',
      panel: ''
    };
  }
}

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
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => string;
  updateLastMessage: (content: string) => void;
  updateLastMessageOptions: (options: string[]) => void;
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
    const { messages, addMessage, updateLastMessage, resetStreamStats, deleteMessage } = get();

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

    // 创建流式JSON解析器
    const jsonParser = new StreamingJSONParser((parseState) => {
      // 实时更新 story 到聊天消息
      if (parseState.story) {
        updateLastMessage(parseState.story);
        set({ streamingContent: parseState.story });
      }

      // 实时更新场景信息到游戏状态
      if (parseState.scene_info) {
        const gameStore = useGameStore.getState();
        const worldUpdates: Partial<WorldState> = {};

        if (parseState.scene_info.location) {
          worldUpdates.location = parseState.scene_info.location;
        }
        if (parseState.scene_info.time) {
          worldUpdates.time = parseState.scene_info.time;
        }

        if (Object.keys(worldUpdates).length > 0) {
          gameStore.updateWorld(worldUpdates);
        }
      }
    });

    try {
      // 构建消息历史
      const chatMessages = previousMessages
        .filter((m) => m.sender !== 'system')
        .map((m) => ({
          role: m.sender === 'player' ? 'user' : 'assistant',
          content: m.content,
        }));

      const response = await fetch(`${config.API_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': getOrCreateUserId(),
        },
        body: JSON.stringify({
          messages: chatMessages,
          stream: true,
          temperature: 0.7,
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

                const elapsedSeconds = (Date.now() - startTime) / 1000;
                const tokensPerSecond = elapsedSeconds > 0 ? outputTokens / elapsedSeconds : 0;

                set((state) => ({
                  streamStats: {
                    ...state.streamStats,
                    outputTokens,
                    tokensPerSecond: Math.round(tokensPerSecond * 10) / 10,
                  },
                }));

                // 使用流式JSON解析器解析内容
                jsonParser.parse(delta);
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
      // 流式解析完成后，保存 options 到最后一条消息
      const finalState = jsonParser.getState();
      if (finalState.options && finalState.options.length > 0) {
        get().updateLastMessageOptions(finalState.options);
      }
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
    const { messages, addMessage, updateLastMessage, resetStreamStats } = get();

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

    // 创建流式JSON解析器
    const jsonParser = new StreamingJSONParser((parseState) => {
      // 实时更新 story 到聊天消息
      if (parseState.story) {
        updateLastMessage(parseState.story);
        set({ streamingContent: parseState.story });
      }

      // 实时更新场景信息到游戏状态
      if (parseState.scene_info) {
        const gameStore = useGameStore.getState();
        const worldUpdates: Partial<WorldState> = {};

        if (parseState.scene_info.location) {
          worldUpdates.location = parseState.scene_info.location;
        }
        if (parseState.scene_info.time) {
          worldUpdates.time = parseState.scene_info.time;
        }

        if (Object.keys(worldUpdates).length > 0) {
          gameStore.updateWorld(worldUpdates);
        }
      }
    });

    try {
      // 只发送当前用户消息，不包含历史聊天记录
      const chatMessages = [{
        role: 'user',
        content: content,
      }];

      const response = await fetch(`${config.API_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': getOrCreateUserId(),
        },
        body: JSON.stringify({
          messages: chatMessages,
          stream: true,
          temperature: 0.7,
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

                // 使用流式JSON解析器解析内容
                jsonParser.parse(delta);
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
      // 流式解析完成后，保存 options 到最后一条消息
      const finalState = jsonParser.getState();
      if (finalState.options && finalState.options.length > 0) {
        get().updateLastMessageOptions(finalState.options);
      }
      set({ isLoading: false, streamingContent: '', abortController: null });
    }
  },
}));
