import { useState, useRef, useEffect } from 'react';
import { Send, Square, Clock, X } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { useGameStore } from '../stores/gameStore';
import { BackpackDialog } from './BackpackDialog';
import { EquipmentDialog } from './EquipmentDialog';

const quickActions = [
  { label: '装备', icon: '🛡️', command: '__equipment__' },
  { label: '背包', icon: '🎒', command: '__backpack__' },
];

export function ChatInput() {
  const { inputValue, setInputValue, sendMessage, isLoading, stopGeneration, streamStats } = useChatStore();
  const { fetchInventory, fetchEquipment, character, interruptAction } = useGameStore();
  const [isFocused, setIsFocused] = useState(false);
  const [backpackOpen, setBackpackOpen] = useState(false);
  const [equipmentOpen, setEquipmentOpen] = useState(false);
  const [busyRemaining, setBusyRemaining] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const busyState = character.busyState;

  // 更新忙碌状态倒计时
  useEffect(() => {
    if (!busyState) {
      setBusyRemaining(0);
      return;
    }

    const updateRemaining = () => {
      const remaining = Math.max(0, Math.ceil((busyState.cooldownEndAt - Date.now()) / 1000));
      setBusyRemaining(remaining);
    };

    updateRemaining();
    const interval = setInterval(updateRemaining, 1000);
    return () => clearInterval(interval);
  }, [busyState]);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const content = inputValue.trim();
    setInputValue('');
    await sendMessage(content);
  };

  const handleInterrupt = async () => {
    await interruptAction();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuickAction = async (command: string) => {
    if (command === '__backpack__') {
      await fetchInventory();
      setBackpackOpen(true);
      return;
    }
    if (command === '__equipment__') {
      await fetchEquipment();
      setEquipmentOpen(true);
      return;
    }
    setInputValue(command);
    textareaRef.current?.focus();
  };

  // 计算上下文百分比
  const contextPercent = Math.round((streamStats.contextTokens / streamStats.contextMax) * 100);

  return (
    <div data-name="chat-input" className="p-4 bg-gradient-to-t from-[#0a0a0f] to-[#0d1f1f] border-t border-[#2d5a5a]/30 flex-shrink-0">
      {/* Busy State Banner */}
      {busyState && busyRemaining > 0 && (
        <div data-name="busy-state" className="flex items-center justify-between gap-3 mb-3 px-4 py-2.5 bg-[#2d5a5a]/20 border border-[#c9a227]/30 rounded-lg">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-[#c9a227] animate-pulse" />
            <span className="text-sm text-[#c9a227]">
              {busyState.action}中... 剩余 {busyRemaining}s
            </span>
          </div>
          <button
            onClick={handleInterrupt}
            className="flex items-center gap-1 px-2 py-1 text-xs text-[#a0c0c0] hover:text-[#e8e4dc] bg-[#1a2f2f]/50 hover:bg-[#2d5a5a]/30 rounded transition-all duration-200"
          >
            <X className="w-3 h-3" />
            <span>中断</span>
          </button>
        </div>
      )}

      {/* Quick Actions */}
      <div data-name="quick-actions" className="flex items-center justify-between gap-2 mb-3">
        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
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

        {/* Stream Stats - 紧凑展示在右侧 */}
        {isLoading && (
          <div data-name="stream-stats" className="flex items-center gap-3 text-xs text-[#5a7a7a] flex-shrink-0">
            <span className="whitespace-nowrap">{streamStats.tokensPerSecond.toFixed(1)} t/s</span>
            <span className="whitespace-nowrap">{contextPercent}% ctx</span>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div
        className={`relative flex items-end gap-3 p-3 bg-[#1a2f2f]/50 rounded-xl transition-all duration-300 ${
          isFocused ? 'shadow-lg shadow-[#3d7a7a]/10' : ''
        }`}
      >
        <div className="flex-1 h-full">
          <textarea
            data-name="input-textarea"
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
            data-name="stop-button"
            onClick={stopGeneration}
            className="flex items-center justify-center w-10 h-10 rounded-lg bg-red-500/80 hover:bg-red-500 transition-all duration-200 shadow-lg shadow-red-500/20"
            title="停止生成"
          >
            <Square className="w-5 h-5 text-white fill-white" />
          </button>
        ) : (
          <button
            data-name="send-button"
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



      <BackpackDialog open={backpackOpen} onClose={() => setBackpackOpen(false)} />
      <EquipmentDialog open={equipmentOpen} onClose={() => setEquipmentOpen(false)} />
    </div>
  );
}
