import type { ChatMessage as ChatMessageType } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessageItem({ message }: ChatMessageProps) {
  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
  };

  if (message.type === 'system') {
    return (
      <div className="flex justify-center my-4">
        <div className="px-4 py-2 bg-[#2d5a5a]/20 border border-[#2d5a5a]/40 rounded-full">
          <span className="text-[#a0c0c0] text-sm">{message.content}</span>
        </div>
      </div>
    );
  }

  if (message.type === 'event') {
    return (
      <div className="flex justify-center my-4">
        <div className="px-4 py-3 bg-gradient-to-r from-[#c9a227]/20 via-[#c9a227]/10 to-[#c9a227]/20 border border-[#c9a227]/40 rounded-lg max-w-[80%]">
          <div className="text-[#c9a227] text-sm text-center">{message.content}</div>
        </div>
      </div>
    );
  }

  const isPlayer = message.sender === 'player';

  return (
    <div className={`flex ${isPlayer ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`flex items-start gap-3 max-w-[80%] ${isPlayer ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div
          className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
            isPlayer
              ? 'bg-gradient-to-br from-[#3d7a7a] to-[#2d5a5a] border border-[#3d9a9a]'
              : 'bg-gradient-to-br from-[#c9a227] to-[#a08020] border border-[#f0d878]'
          }`}
        >
          <span className="text-lg">{isPlayer ? '👤' : message.senderAvatar || '🧙'}</span>
        </div>

        {/* Message Content */}
        <div className={`flex flex-col ${isPlayer ? 'items-end' : 'items-start'}`}>
          {/* Sender Name */}
          {!isPlayer && message.senderName && (
            <span className="text-xs text-[#a0c0c0] mb-1">{message.senderName}</span>
          )}

          {/* Message Bubble */}
          <div
            className={`px-4 py-3 rounded-2xl ${
              isPlayer
                ? 'bg-gradient-to-br from-[#2d5a5a] to-[#1a3a3a] border border-[#3d7a7a]/50 rounded-tr-sm'
                : 'bg-gradient-to-br from-[#1a2f2f] to-[#0d1f1f] border border-[#2d5a5a]/50 rounded-tl-sm'
            }`}
          >
            <div className="markdown-body text-[#e8e4dc] text-sm leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          </div>

          {/* Timestamp */}
          <span className="text-[10px] text-[#5a7a7a] mt-1">{formatTime(message.timestamp)}</span>
        </div>
      </div>
    </div>
  );
}
