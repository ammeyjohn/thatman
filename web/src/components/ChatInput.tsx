import { useState, useRef } from 'react';
import { Send, Square } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';

const quickActions = [
  { label: '修炼', icon: '✨', command: '开始修炼' },
  { label: '探索', icon: '🔍', command: '探索周围' },
  { label: '对话', icon: '💬', command: '与村长对话' },
  { label: '背包', icon: '🎒', command: '查看背包' },
];

export function ChatInput() {
  const { inputValue, setInputValue, sendMessage, isLoading, stopGeneration, streamStats } = useChatStore();
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const content = inputValue.trim();
    setInputValue('');
    await sendMessage(content);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuickAction = (command: string) => {
    setInputValue(command);
    textareaRef.current?.focus();
  };

  // 计算上下文百分比
  const contextPercent = Math.round((streamStats.contextTokens / streamStats.contextMax) * 100);

  return (
    <div className="p-4 bg-gradient-to-t from-[#0a0a0f] to-[#0d1f1f] border-t border-[#2d5a5a]/30">
      {/* Quick Actions */}
      <div className="flex gap-2 mb-3 overflow-x-auto pb-2 scrollbar-hide">
        {quickActions.map((action) => (
          <button
            key={action.label}
            onClick={() => handleQuickAction(action.command)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1a2f2f]/50 hover:bg-[#2d5a5a]/30 border border-[#2d5a5a]/30 hover:border-[#3d7a7a]/50 rounded-full transition-all duration-200 flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className="text-sm">{action.icon}</span>
            <span className="text-xs text-[#a0c0c0] hover:text-[#e8e4dc]">{action.label}</span>
          </button>
        ))}
      </div>

      {/* Input Area */}
      <div
        className={`relative flex items-end gap-3 p-3 bg-[#1a2f2f]/50 rounded-xl transition-all duration-300 ${
          isFocused ? 'shadow-lg shadow-[#3d7a7a]/10' : ''
        }`}
      >
        <div className="flex-1 h-full">
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={isLoading ? 'AI 思考中...' : '输入指令与AI交互...'}
            rows={3}
            disabled={isLoading}
            className="w-full h-full bg-transparent text-[#e8e4dc] placeholder-[#5a7a7a] text-sm resize-none outline-none scrollbar-hide disabled:opacity-50 border-0 focus:ring-0 focus:border-0"
            style={{ minHeight: '72px' }}
          />
        </div>

        {isLoading ? (
          <button
            onClick={stopGeneration}
            className="flex items-center justify-center w-10 h-10 rounded-lg bg-red-500/80 hover:bg-red-500 transition-all duration-200 shadow-lg shadow-red-500/20"
            title="停止生成"
          >
            <Square className="w-5 h-5 text-white fill-white" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!inputValue.trim()}
            className={`flex items-center justify-center w-10 h-10 rounded-lg transition-all duration-200 ${
              inputValue.trim()
                ? 'bg-gradient-to-br from-[#c9a227] to-[#a08020] hover:from-[#d0aa30] hover:to-[#b09030] shadow-lg shadow-[#c9a227]/20'
                : 'bg-[#2d5a5a]/30 cursor-not-allowed'
            }`}
          >
            <Send className={`w-5 h-5 ${inputValue.trim() ? 'text-[#0a0a0f]' : 'text-[#5a7a7a]'}`} />
          </button>
        )}
      </div>

      {/* Stream Stats */}
      {isLoading && (
        <div className="flex items-center justify-center gap-6 mt-3 text-xs text-[#5a7a7a]">
          <span>
            Context: {streamStats.contextTokens}/{streamStats.contextMax} ({contextPercent}%)
          </span>
          <span>
            Output: {streamStats.outputTokens}/{streamStats.outputMax === null ? '∞' : streamStats.outputMax}
          </span>
          <span>{streamStats.tokensPerSecond.toFixed(1)} t/s</span>
        </div>
      )}
    </div>
  );
}
