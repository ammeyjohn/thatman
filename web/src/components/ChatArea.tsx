import { useEffect, useRef } from 'react';
import { useChatStore } from '../stores/chatStore';
import { ChatMessageItem } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { MessageSquare } from 'lucide-react';

export function ChatArea() {
  const { messages, sendMessage } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div data-name="chat-area" className="flex-1 flex flex-col min-w-0 bg-gradient-to-b from-[#0a0a0f] via-[#0d1515] to-[#0a0a0f] overflow-hidden">
      {/* Header */}
      <div data-name="chat-header" className="px-6 py-4 border-b border-[#2d5a5a]/30 flex items-center justify-between bg-[#0d1f1f]/50 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#2d5a5a] to-[#1a3a3a] border border-[#3d7a7a]/50 flex items-center justify-center">
            <MessageSquare className="w-5 h-5 text-[#3d9a9a]" />
          </div>
          <div>
            <h2 className="text-[#e8e4dc] font-bold text-lg" style={{ fontFamily: 'Noto Serif SC, serif' }}>
              修仙对话
            </h2>
            <p className="text-xs text-[#5a7a7a]">与NPC交互，探索青墟世界</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-[#4ec94e] rounded-full animate-pulse"></span>
          <span className="text-xs text-[#5a7a7a]">AI 在线</span>
        </div>
      </div>

      {/* Messages */}
      <div
        data-name="message-list"
        ref={containerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-4 scrollbar-thin scrollbar-thumb-[#2d5a5a] scrollbar-track-transparent min-w-0"
      >
        {messages.length === 0 ? (
          <div data-name="empty-state" className="flex flex-col items-center justify-center h-full text-[#5a7a7a]">
            <div className="w-16 h-16 rounded-full bg-[#1a2f2f]/50 flex items-center justify-center mb-4">
              <MessageSquare className="w-8 h-8" />
            </div>
            <p className="text-sm">开始你的修仙之旅</p>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <ChatMessageItem
                key={message.id}
                message={message}
                onOptionClick={(option) => sendMessage(option)}
              />
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <ChatInput />
    </div>
  );
}
