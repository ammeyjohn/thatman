import { useEffect, useRef } from 'react';
import { useChatStore } from '../stores/chatStore';
import { ChatMessageItem } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { MessageSquare, Loader2 } from 'lucide-react';

export function ChatArea() {
  const { messages, sendMessage, hasMoreHistory, isLoadingHistory, loadMoreHistory } = useChatStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const shouldRestoreScroll = useRef(false);
  const prevScrollHeight = useRef(0);
  const isNearBottom = useRef(true);

  useEffect(() => {
    if (containerRef.current) {
      if (shouldRestoreScroll.current) {
        const newScrollHeight = containerRef.current.scrollHeight;
        containerRef.current.scrollTop = newScrollHeight - prevScrollHeight.current;
        shouldRestoreScroll.current = false;
      } else if (isNearBottom.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    }
  }, [messages]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;

    // 更新是否在底部
    isNearBottom.current = scrollTop + clientHeight >= scrollHeight - 50;

    // 滚动到顶部附近时加载更多历史
    if (scrollTop < 50 && hasMoreHistory && !isLoadingHistory) {
      prevScrollHeight.current = scrollHeight;
      shouldRestoreScroll.current = true;
      loadMoreHistory();
    }
  };

  return (
    <div data-name="chat-area" className="flex-1 flex flex-col min-w-0 min-h-0 bg-gradient-to-b from-[#0a0a0f] via-[#0d1515] to-[#0a0a0f] overflow-hidden">
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
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-6 py-4 scrollbar-thin scrollbar-thumb-[#2d5a5a] scrollbar-track-transparent min-w-0"
      >
        {isLoadingHistory && (
          <div className="flex items-center justify-center py-4 text-[#5a7a7a]">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            <span className="text-xs">加载更多历史...</span>
          </div>
        )}
        {messages.length === 0 && !isLoadingHistory ? (
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
          </>
        )}
      </div>

      {/* Input */}
      <ChatInput />
    </div>
  );
}
