import { create } from 'zustand';
import type { ChatMessage } from '../types';

interface ChatState {
  messages: ChatMessage[];
  inputValue: string;
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  setInputValue: (value: string) => void;
  clearMessages: () => void;
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

export const useChatStore = create<ChatState>((set) => ({
  messages: initialMessages,
  inputValue: '',
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
}));
