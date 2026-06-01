import { create } from 'zustand';
import type { ChatMessage } from '../types';
import { config } from '../config';

let messageIdCounter = 0;
const generateId = () => {
  messageIdCounter += 1;
  return `${Date.now()}-${messageIdCounter}`;
};

interface ChatState {
  messages: ChatMessage[];
  inputValue: string;
  isLoading: boolean;
  streamingContent: string;
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => string;
  updateLastMessage: (content: string) => void;
  setInputValue: (value: string) => void;
  setStreamingContent: (content: string) => void;
  clearMessages: () => void;
  sendMessage: (content: string) => Promise<void>;
}

const initialMessages: ChatMessage[] = [];

export const useChatStore = create<ChatState>((set, get) => ({
  messages: initialMessages,
  inputValue: '',
  isLoading: false,
  streamingContent: '',

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

  setInputValue: (value) => set({ inputValue: value }),

  setStreamingContent: (content) => set({ streamingContent: content }),

  clearMessages: () => set({ messages: [] }),

  sendMessage: async (content: string) => {
    const { messages, addMessage, updateLastMessage } = get();

    // 添加用户消息
    addMessage({
      sender: 'player',
      content: content,
      type: 'normal',
    });

    set({ isLoading: true, streamingContent: '' });

    // 先添加一个空的AI消息，用于流式更新
    addMessage({
      sender: 'npc',
      senderName: '云溪村长',
      senderAvatar: '👴',
      content: '',
      type: 'normal',
    });

    try {
      // 构建消息历史
      const chatMessages = messages
        .filter((m) => m.sender !== 'system')
        .map((m) => ({
          role: m.sender === 'player' ? 'user' : 'assistant',
          content: m.content,
        }));

      // 添加当前用户消息
      chatMessages.push({
        role: 'user',
        content: content,
      });

      const response = await fetch(`${config.API_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: chatMessages,
          stream: true,
          temperature: 0.7,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let fullContent = '';

      if (!reader) {
        throw new Error('无法获取响应流');
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

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
                fullContent += delta;
                // 去除文本中间的空行
                const cleanedContent = fullContent.replace(/\n\s*\n+/g, '\n');
                updateLastMessage(cleanedContent);
                set({ streamingContent: cleanedContent });
              }
            } catch (e) {
              // 忽略解析错误的行
            }
          }
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      updateLastMessage(`发送失败: ${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      set({ isLoading: false, streamingContent: '' });
    }
  },
}));
