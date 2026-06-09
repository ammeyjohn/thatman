import { useMemo } from 'react';
import { X } from 'lucide-react';
import { useGameStore } from '../stores/gameStore';
import type { InventoryItem } from '../types';

interface BackpackDialogProps {
  open: boolean;
  onClose: () => void;
}

// 物品类型 -> 图标映射
const TYPE_ICON_MAP: Record<string, string> = {
  '丹药': '⚗️',
  '法宝': '🗡️',
  '材料': '🏺',
  '天材地宝': '🌸',
};

// 物品类型排序顺序
const TYPE_ORDER = ['丹药', '法宝', '材料', '天材地宝', '其他'];

function getTypeIcon(type: string): string {
  return TYPE_ICON_MAP[type] ?? '📦';
}

function getTypeLabel(type: string): string {
  return TYPE_ICON_MAP[type] ? type : '其他';
}

function normalizeItem(item: unknown, index: number): InventoryItem | null {
  if (!item || typeof item !== 'object') return null;
  const raw = item as Record<string, unknown>;
  const name = typeof raw.name === 'string' && raw.name.trim() ? raw.name.trim() : '未知物品';
  const type = typeof raw.type === 'string' && raw.type.trim() ? raw.type.trim() : '其他';
  const description = typeof raw.description === 'string' ? raw.description : '';
  const quantity = typeof raw.quantity === 'number' && !isNaN(raw.quantity) ? Math.max(1, raw.quantity) : 1;
  const id = typeof raw.id === 'string' && raw.id.trim() ? raw.id.trim() : `item_${index}`;
  return { id, name, type, description, quantity };
}

function groupItemsByType(inventory: unknown[]): Map<string, InventoryItem[]> {
  const groups = new Map<string, InventoryItem[]>();
  for (let i = 0; i < inventory.length; i++) {
    const item = normalizeItem(inventory[i], i);
    if (!item) continue;
    const label = getTypeLabel(item.type);
    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label)!.push(item);
  }
  // 按预定义顺序排序
  const sorted = new Map<string, InventoryItem[]>();
  for (const type of TYPE_ORDER) {
    if (groups.has(type)) {
      sorted.set(type, groups.get(type)!);
    }
  }
  return sorted;
}

export function BackpackDialog({ open, onClose }: BackpackDialogProps) {
  const { character } = useGameStore();
  const rawInventory = character.inventory ?? [];

  const normalizedInventory = useMemo(
    () => rawInventory.map((item, index) => normalizeItem(item, index)).filter((item): item is InventoryItem => item !== null),
    [rawInventory]
  );

  const groupedItems = useMemo(
    () => groupItemsByType(normalizedInventory),
    [normalizedInventory]
  );
  const isEmpty = normalizedInventory.length === 0;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-lg mx-4 rounded-xl border border-[#2d5a5a]/50 shadow-2xl shadow-black/50 overflow-hidden"
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
          ╔══════════════════════════════════════════════════════════════╗
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#2d5a5a]/30">
          <div className="flex items-center gap-2">
            <span className="text-xl">🎒</span>
            <h2
              className="text-lg font-bold tracking-wider"
              style={{ color: '#C9A962' }}
            >
              储物背包
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
        <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
          {isEmpty ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center py-12">
              <span className="text-5xl mb-4 opacity-40">📦</span>
              <p className="text-[#7F8C8D] text-base" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                背包空空如也
              </p>
              <p className="text-[#7F8C8D]/60 text-xs mt-2" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                探索修仙世界，收集天材地宝
              </p>
            </div>
          ) : (
            /* Grouped items */
            <div className="space-y-4">
              {Array.from(groupedItems.entries()).map(([type, items]) => (
                <div key={type}>
                  {/* Type group header */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-base">{getTypeIcon(type)}</span>
                    <span
                      className="text-sm font-medium tracking-wide"
                      style={{ color: '#4ECDC4' }}
                    >
                      {type}
                    </span>
                    <span className="text-[#7F8C8D] text-xs">({items.length})</span>
                  </div>

                  {/* Section separator */}
                  <div
                    className="text-[#2d5a5a]/50 text-[10px] leading-none mb-2 select-none overflow-hidden whitespace-nowrap"
                    style={{ fontFamily: 'monospace' }}
                  >
                    ◈ ───────────────────────────────────────────────────────── ◈
                  </div>

                  {/* Items list */}
                  <div className="space-y-1">
                    {items.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-start gap-3 px-3 py-2.5 rounded-lg transition-colors duration-200 hover:bg-[#2d5a5a]/15 cursor-default group"
                      >
                        {/* Item icon */}
                        <span className="text-base mt-0.5 shrink-0">{getTypeIcon(item.type)}</span>

                        {/* Item info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span
                              className="text-sm font-medium truncate"
                              style={{ color: '#E8E8E8' }}
                            >
                              {item.name}
                            </span>
                            {item.quantity > 1 && (
                              <span
                                className="text-xs shrink-0 px-1.5 py-0.5 rounded bg-[#2d5a5a]/20"
                                style={{ color: '#7F8C8D' }}
                              >
                                x{item.quantity}
                              </span>
                            )}
                          </div>
                          {item.description && (
                            <p
                              className="text-xs mt-1 leading-relaxed line-clamp-2"
                              style={{ color: '#7F8C8D' }}
                            >
                              {item.description}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer with item count */}
        {!isEmpty && (
          <div className="px-5 py-2.5 border-t border-[#2d5a5a]/30 bg-[#0D0D0D]/50">
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: '#7F8C8D' }}>
                共 {normalizedInventory.length} 种物品
              </span>
              <span className="text-xs" style={{ color: '#7F8C8D' }}>
                总计 {normalizedInventory.reduce((sum, item) => sum + item.quantity, 0)} 件
              </span>
            </div>
          </div>
        )}

        {/* Bottom ASCII border */}
        <div
          className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden"
          style={{ fontFamily: 'monospace' }}
        >
          ╚══════════════════════════════════════════════════════════════╝
        </div>
      </div>
    </div>
  );
}
