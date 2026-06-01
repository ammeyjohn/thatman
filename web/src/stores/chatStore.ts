import { create } from 'zustand';
import type { ChatMessage } from '../types';
import { config } from '../config';

interface ChatState {
  messages: ChatMessage[];
  inputValue: string;
  isLoading: boolean;
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  setInputValue: (value: string) => void;
  clearMessages: () => void;
  sendMessage: (content: string) => Promise<void>;
}

const initialMessages: ChatMessage[] = [
  {
    id: '1',
    sender: 'system',
    content: '欢迎来到《青墟灵修志》，修仙之路漫漫，愿道友道心坚定，早日飞升。',
    timestamp: Date.now() - 60000,
    type: 'system',
  },
  {
    id: '2',
    sender: 'npc',
    senderName: '云溪村长',
    senderAvatar: '👴',
    content: '小友，看你气宇不凡，可是来我云溪村寻求机缘的？今夜正值灵潮，灵气充盈，正是修炼的好时机。',
    timestamp: Date.now() - 30000,
    type: 'normal',
  },
];

export const useChatStore = create<ChatState>((set, get) => ({
  messages: initialMessages,
  inputValue: '',
  isLoading: false,

  addMessage: (message) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          ...message,
          id: Date.now().toString(),
          timestamp: Date.now(),
        },
      ],
    })),

  setInputValue: (value) => set({ inputValue: value }),

  clearMessages: () => set({ messages: [] }),

  sendMessage: async (content: string) => {
    const { messages, addMessage } = get();

    // 添加用户消息
    addMessage({
      sender: 'player',
      content: content,
      type: 'normal',
    });

    set({ isLoading: true });

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
          stream: false,
          temperature: 0.7,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      if (data.error) {
        throw new Error(data.error.message || 'API 请求失败');
      }

      // 添加AI回复
      const aiContent = data.choices?.[0]?.message?.content || '...';
      addMessage({
        sender: 'npc',
        senderName: '云溪村长',
        senderAvatar: '👴',
        content: aiContent,
        type: 'normal',
      });
    } catch (error) {
      console.error('发送消息失败:', error);
      addMessage({
        sender: 'system',
        content: `发送失败: ${error instanceof Error ? error.message : '未知错误'}`,
        type: 'system',
      });
    } finally {
      set({ isLoading: false });
    }
  },
}));
