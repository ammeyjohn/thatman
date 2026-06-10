import { useState } from 'react';
import { X, BookOpen, MapPin, Clock, ChevronRight } from 'lucide-react';
import { useGameStore } from '../stores/gameStore';
import type { CharacterHistory, HistoryEntry } from '../types';

interface HistoryDialogProps {
  open: boolean;
  onClose: () => void;
}

export function HistoryDialog({ open, onClose }: HistoryDialogProps) {
  const { historyList, historyDates, fetchHistory } = useGameStore();
  const [selectedDate, setSelectedDate] = useState<string>('');

  if (!open) return null;

  const isEmpty = historyDates.length === 0;

  const handleDateSelect = async (date: string) => {
    setSelectedDate(date);
    await fetchHistory(date);
  };

  const handleShowAll = async () => {
    setSelectedDate('');
    await fetchHistory();
  };

  // 获取当前选中的历史详情
  const selectedHistory = selectedDate
    ? historyList.find((h) => h.gameDate === selectedDate)
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-4xl mx-4 rounded-xl border border-[#2d5a5a]/50 shadow-2xl shadow-black/50 overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, #1A1A2E 0%, #0D0D0D 100%)',
          fontFamily: 'Noto Serif SC, serif',
        }}
      >
        {/* Top ASCII border */}
        <div
          className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden"
          style={{ fontFamily: 'monospace' }}
        >
          ╔════════════════════════════════════════════════════════════════════════════════════════════════════╗
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#2d5a5a]/30">
          <div className="flex items-center gap-2">
            <span className="text-xl">📖</span>
            <h2
              className="text-lg font-bold tracking-wider"
              style={{ color: '#C9A962' }}
            >
              历史进程
            </h2>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-md bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#C9A962] hover:border-[#C9A962]/50 transition-colors duration-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[75vh] overflow-hidden flex">
          {isEmpty ? (
            /* Empty state */
            <div className="flex-1 flex flex-col items-center justify-center py-16">
              <span className="text-5xl mb-4 opacity-40">📖</span>
              <p className="text-[#7F8C8D] text-base">尚无历史记录</p>
              <p className="text-[#7F8C8D]/60 text-xs mt-2">与世界交互时，历史进程将被自动记录</p>
            </div>
          ) : (
            <>
              {/* Left: Date list */}
              <div className="w-56 flex-shrink-0 border-r border-[#2d5a5a]/30 overflow-y-auto">
                {/* All dates button */}
                <button
                  onClick={handleShowAll}
                  className={`w-full text-left px-4 py-2.5 text-sm transition-colors duration-200 border-b border-[#2d5a5a]/20 ${
                    !selectedDate
                      ? 'bg-[#2d5a5a]/20 text-[#C9A962]'
                      : 'text-[#a0c0c0] hover:bg-[#2d5a5a]/10 hover:text-[#e8e4dc]'
                  }`}
                >
                  全部日程
                </button>
                {historyDates.map((date) => (
                  <button
                    key={date}
                    onClick={() => handleDateSelect(date)}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors duration-200 border-b border-[#2d5a5a]/10 flex items-center gap-2 ${
                      selectedDate === date
                        ? 'bg-[#2d5a5a]/20 text-[#C9A962]'
                        : 'text-[#a0c0c0] hover:bg-[#2d5a5a]/10 hover:text-[#e8e4dc]'
                    }`}
                  >
                    <ChevronRight className="w-3 h-3 flex-shrink-0 opacity-50" />
                    <span className="truncate">{date}</span>
                  </button>
                ))}
              </div>

              {/* Right: History details */}
              <div className="flex-1 overflow-y-auto px-5 py-4">
                {selectedDate && selectedHistory ? (
                  <DateHistoryDetail history={selectedHistory} />
                ) : (
                  <AllHistoryList historyList={historyList} />
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {!isEmpty && (
          <div className="px-5 py-2.5 border-t border-[#2d5a5a]/30 bg-[#0D0D0D]/50">
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: '#7F8C8D' }}>
                共 {historyDates.length} 日记录
              </span>
              <span className="text-xs" style={{ color: '#7F8C8D' }}>
                {selectedDate ? `查看: ${selectedDate}` : '查看全部'}
              </span>
            </div>
          </div>
        )}

        {/* Bottom ASCII border */}
        <div
          className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden"
          style={{ fontFamily: 'monospace' }}
        >
          ╚════════════════════════════════════════════════════════════════════════════════════════════════════╝
        </div>
      </div>
    </div>
  );
}

function DateHistoryDetail({ history }: { history: CharacterHistory }) {
  return (
    <div className="space-y-4">
      {/* Daily summary */}
      {history.dailySummary && (
        <div className="px-4 py-3 rounded-lg bg-[#2d5a5a]/10 border border-[#2d5a5a]/20">
          <div className="flex items-center gap-2 mb-1.5">
            <BookOpen className="w-4 h-4" style={{ color: '#C9A962' }} />
            <span className="text-sm font-medium" style={{ color: '#C9A962' }}>
              当日总结
            </span>
          </div>
          <p className="text-sm leading-relaxed" style={{ color: '#e8e4dc' }}>
            {history.dailySummary}
          </p>
        </div>
      )}

      {/* Entries timeline */}
      <div className="space-y-3">
        {history.entries.map((entry, index) => (
          <HistoryEntryCard key={index} entry={entry} isLast={index === history.entries.length - 1} />
        ))}
      </div>
    </div>
  );
}

function HistoryEntryCard({ entry, isLast }: { entry: HistoryEntry; isLast: boolean }) {
  return (
    <div className="flex gap-3">
      {/* Timeline line */}
      <div className="flex flex-col items-center">
        <div className="w-2 h-2 rounded-full bg-[#4ECDC4] mt-1.5 flex-shrink-0" />
        {!isLast && <div className="w-px flex-1 bg-[#2d5a5a]/30 my-1" />}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-3">
        {/* Period & Location */}
        <div className="flex items-center gap-3 mb-1">
          {entry.period && (
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" style={{ color: '#4ECDC4' }} />
              <span className="text-xs" style={{ color: '#4ECDC4' }}>
                {entry.period}
              </span>
            </div>
          )}
          {entry.location && (
            <div className="flex items-center gap-1">
              <MapPin className="w-3 h-3" style={{ color: '#7F8C8D' }} />
              <span className="text-xs" style={{ color: '#7F8C8D' }}>
                {entry.location}
              </span>
            </div>
          )}
        </div>

        {/* Summary */}
        <p className="text-sm leading-relaxed" style={{ color: '#e8e4dc' }}>
          {entry.summary}
        </p>

        {/* Key changes */}
        {entry.keyChanges.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {entry.keyChanges.map((change, i) => (
              <span
                key={i}
                className="text-[10px] px-1.5 py-0.5 rounded bg-[#C9A962]/10 text-[#C9A962] border border-[#C9A962]/20"
              >
                {change}
              </span>
            ))}
          </div>
        )}

        {/* Realm snapshot */}
        {entry.realmSnapshot && (
          <p className="text-[10px] mt-1.5" style={{ color: '#5a7a7a' }}>
            境界: {entry.realmSnapshot}
          </p>
        )}
      </div>
    </div>
  );
}

function AllHistoryList({ historyList }: { historyList: CharacterHistory[] }) {
  if (historyList.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <p className="text-[#7F8C8D] text-sm">选择左侧日程查看详情</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {historyList.map((history) => (
        <div key={history.gameDate} className="px-4 py-3 rounded-lg bg-[#2d5a5a]/5 border border-[#2d5a5a]/15 hover:bg-[#2d5a5a]/10 transition-colors duration-200">
          {/* Date header */}
          <div className="flex items-center gap-2 mb-2">
            <BookOpen className="w-4 h-4" style={{ color: '#C9A962' }} />
            <span className="text-sm font-medium" style={{ color: '#C9A962' }}>
              {history.gameDate}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2d5a5a]/20 text-[#7F8C8D]">
              {history.entries.length} 条记录
            </span>
          </div>

          {/* Daily summary */}
          {history.dailySummary && (
            <p className="text-sm leading-relaxed mb-2" style={{ color: '#e8e4dc' }}>
              {history.dailySummary}
            </p>
          )}

          {/* Entry summaries */}
          <div className="space-y-1">
            {history.entries.map((entry, index) => (
              <div key={index} className="flex items-start gap-2">
                <span className="text-[10px] flex-shrink-0 mt-0.5" style={{ color: '#4ECDC4' }}>
                  {entry.period}
                </span>
                <span className="text-xs leading-relaxed" style={{ color: '#a0c0c0' }}>
                  {entry.summary}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
