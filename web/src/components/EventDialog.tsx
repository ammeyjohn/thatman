import { useState } from 'react';
import { X, Trash2, Clock, CheckCircle } from 'lucide-react';
import { useGameStore } from '../stores/gameStore';
import { ConfirmDialog } from './ConfirmDialog';
import type { KeyEvent } from '../types';

interface EventDialogProps {
  open: boolean;
  onClose: () => void;
}

function formatTime(isoString: string): string {
  if (!isoString) return '';
  try {
    const date = new Date(isoString);
    const month = date.getMonth() + 1;
    const day = date.getDate();
    const hour = date.getHours().toString().padStart(2, '0');
    const minute = date.getMinutes().toString().padStart(2, '0');
    return `${month}月${day}日 ${hour}:${minute}`;
  } catch {
    return '';
  }
}

export function EventDialog({ open, onClose }: EventDialogProps) {
  const { keyEvents, deleteKeyEvent } = useGameStore();
  const [deleteTarget, setDeleteTarget] = useState<KeyEvent | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!open) return null;

  const ongoingEvents = keyEvents.filter((e) => e.status === 'ongoing');
  const completedEvents = keyEvents.filter((e) => e.status === 'completed');
  const isEmpty = keyEvents.length === 0;

  const handleDeleteClick = (event: KeyEvent) => {
    setDeleteTarget(event);
    setConfirmOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (deleteTarget) {
      await deleteKeyEvent(deleteTarget.id);
    }
    setConfirmOpen(false);
    setDeleteTarget(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog - 尺寸更大 */}
      <div
        className="relative w-full max-w-2xl mx-4 rounded-xl border border-[#2d5a5a]/50 shadow-2xl shadow-black/50 overflow-hidden"
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
          ╔════════════════════════════════════════════════════════════════════════════════╗
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#2d5a5a]/30">
          <div className="flex items-center gap-2">
            <span className="text-xl">📜</span>
            <h2
              className="text-lg font-bold tracking-wider"
              style={{ color: '#C9A962' }}
            >
              关键事件
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
        <div className="max-h-[75vh] overflow-y-auto px-5 py-4">
          {isEmpty ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center py-16">
              <span className="text-5xl mb-4 opacity-40">📜</span>
              <p className="text-[#7F8C8D] text-base" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                尚无关键事件记录
              </p>
              <p className="text-[#7F8C8D]/60 text-xs mt-2" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                与世界交互时，重要事件将被自动记录
              </p>
            </div>
          ) : (
            <div className="space-y-5">
              {/* 进行中事件 */}
              {ongoingEvents.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Clock className="w-4 h-4" style={{ color: '#4ECDC4' }} />
                    <span
                      className="text-sm font-medium tracking-wide"
                      style={{ color: '#4ECDC4' }}
                    >
                      进行中
                    </span>
                    <span className="text-[#7F8C8D] text-xs">({ongoingEvents.length})</span>
                  </div>
                  <div
                    className="text-[#2d5a5a]/50 text-[10px] leading-none mb-2 select-none overflow-hidden whitespace-nowrap"
                    style={{ fontFamily: 'monospace' }}
                  >
                    ◈ ────────────────────────────────────────────────────────────────────── ◈
                  </div>
                  <div className="space-y-2">
                    {ongoingEvents.map((event) => (
                      <EventCard key={event.id} event={event} onDelete={handleDeleteClick} />
                    ))}
                  </div>
                </div>
              )}

              {/* 已完成事件 */}
              {completedEvents.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="w-4 h-4" style={{ color: '#7F8C8D' }} />
                    <span
                      className="text-sm font-medium tracking-wide"
                      style={{ color: '#7F8C8D' }}
                    >
                      已完成
                    </span>
                    <span className="text-[#7F8C8D] text-xs">({completedEvents.length})</span>
                  </div>
                  <div
                    className="text-[#2d5a5a]/50 text-[10px] leading-none mb-2 select-none overflow-hidden whitespace-nowrap"
                    style={{ fontFamily: 'monospace' }}
                  >
                    ◈ ────────────────────────────────────────────────────────────────────── ◈
                  </div>
                  <div className="space-y-2">
                    {completedEvents.map((event) => (
                      <EventCard key={event.id} event={event} onDelete={handleDeleteClick} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer with event count */}
        {!isEmpty && (
          <div className="px-5 py-2.5 border-t border-[#2d5a5a]/30 bg-[#0D0D0D]/50">
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: '#7F8C8D' }}>
                共 {keyEvents.length} 个事件
              </span>
              <span className="text-xs" style={{ color: '#7F8C8D' }}>
                进行中 {ongoingEvents.length} · 已完成 {completedEvents.length}
              </span>
            </div>
          </div>
        )}

        {/* Bottom ASCII border */}
        <div
          className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden"
          style={{ fontFamily: 'monospace' }}
        >
          ╚════════════════════════════════════════════════════════════════════════════════╝
        </div>
      </div>

      {/* Confirm Delete Dialog */}
      <ConfirmDialog
        open={confirmOpen}
        onClose={() => {
          setConfirmOpen(false);
          setDeleteTarget(null);
        }}
        onConfirm={handleConfirmDelete}
        title="删除事件"
        message={`确定要删除事件「${deleteTarget?.title || ''}」吗？此操作不可撤销。`}
      />
    </div>
  );
}

function EventCard({ event, onDelete }: { event: KeyEvent; onDelete: (event: KeyEvent) => void }) {
  const isOngoing = event.status === 'ongoing';

  return (
    <div
      className="flex items-start gap-3 px-4 py-3 rounded-lg transition-colors duration-200 hover:bg-[#2d5a5a]/15 group"
    >
      {/* Status indicator */}
      <div className="mt-1 shrink-0">
        <div
          className={`w-2 h-2 rounded-full ${isOngoing ? 'bg-[#4ECDC4] animate-pulse' : 'bg-[#7F8C8D]'}`}
        />
      </div>

      {/* Event info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="text-sm font-medium truncate"
            style={{ color: isOngoing ? '#E8E8E8' : '#A0A0A0' }}
          >
            {event.title}
          </span>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
              isOngoing
                ? 'bg-[#4ECDC4]/15 text-[#4ECDC4]'
                : 'bg-[#7F8C8D]/15 text-[#7F8C8D]'
            }`}
          >
            {isOngoing ? '进行中' : '已完成'}
          </span>
        </div>
        {event.description && (
          <p
            className="text-xs mt-1 leading-relaxed line-clamp-2"
            style={{ color: '#7F8C8D' }}
          >
            {event.description}
          </p>
        )}
        {event.createdAt && (
          <p className="text-[10px] mt-1.5" style={{ color: '#5a7a7a' }}>
            {formatTime(event.createdAt)}
          </p>
        )}
      </div>

      {/* Delete button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(event);
        }}
        className="shrink-0 p-1.5 rounded-md text-[#5a7a7a] hover:text-red-400 hover:bg-red-400/10 transition-colors duration-200 opacity-0 group-hover:opacity-100 cursor-pointer"
        title="删除事件"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
