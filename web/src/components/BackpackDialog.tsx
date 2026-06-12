import { useMemo, useState, useRef, useEffect, useCallback } from 'react';
import { X, Trash2 } from 'lucide-react';
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

// 物品类型 -> 格子颜色映射
const TYPE_COLOR_MAP: Record<string, { bg: string; border: string; hoverBg: string }> = {
  '丹药': { bg: 'bg-purple-900/40', border: 'border-purple-500/30', hoverBg: 'hover:bg-purple-800/50' },
  '法宝': { bg: 'bg-orange-900/40', border: 'border-orange-500/30', hoverBg: 'hover:bg-orange-800/50' },
  '材料': { bg: 'bg-green-900/40', border: 'border-green-500/30', hoverBg: 'hover:bg-green-800/50' },
  '天材地宝': { bg: 'bg-yellow-900/40', border: 'border-yellow-500/30', hoverBg: 'hover:bg-yellow-800/50' },
  '其他': { bg: 'bg-gray-800/40', border: 'border-gray-500/30', hoverBg: 'hover:bg-gray-700/50' },
};

function getTypeIcon(type: string): string {
  return TYPE_ICON_MAP[type] ?? '📦';
}

function getTypeLabel(type: string): string {
  return TYPE_ICON_MAP[type] ? type : '其他';
}

function getTypeColor(type: string) {
  return TYPE_COLOR_MAP[type] ?? TYPE_COLOR_MAP['其他'];
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

// Tooltip 组件
function ItemTooltip({ item, position }: { item: InventoryItem; position: { x: number; y: number } }) {
  return (
    <div
      className="fixed z-[60] pointer-events-none"
      style={{ left: position.x + 12, top: position.y + 12 }}
    >
      <div
        className="rounded-lg border border-[#2d5a5a]/60 shadow-xl shadow-black/60 px-3 py-2.5 max-w-[220px]"
        style={{ background: 'linear-gradient(180deg, #1A1A2E 0%, #0D0D0D 100%)' }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm">{getTypeIcon(item.type)}</span>
          <span className="text-sm font-medium" style={{ color: '#C9A962' }}>
            {item.name}
          </span>
        </div>
        <div className="text-xs mb-1" style={{ color: '#4ECDC4' }}>
          {getTypeLabel(item.type)}
        </div>
        {item.description && (
          <p className="text-xs leading-relaxed" style={{ color: '#7F8C8D' }}>
            {item.description}
          </p>
        )}
        <div className="text-xs mt-1.5 pt-1.5 border-t border-[#2d5a5a]/30" style={{ color: '#7F8C8D' }}>
          数量: {item.quantity}
        </div>
      </div>
    </div>
  );
}

// 上下文菜单组件
function ContextMenu({
  item,
  position,
  onDiscard,
  onClose,
}: {
  item: InventoryItem;
  position: { x: number; y: number };
  onDiscard: () => void;
  onClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  // 确保菜单不超出视口
  const adjustedX = Math.min(position.x, window.innerWidth - 160);
  const adjustedY = Math.min(position.y, window.innerHeight - 100);

  return (
    <div
      ref={menuRef}
      className="fixed z-[60]"
      style={{ left: adjustedX, top: adjustedY }}
    >
      <div
        className="rounded-lg border border-[#2d5a5a]/60 shadow-xl shadow-black/60 py-1.5 min-w-[140px]"
        style={{ background: 'linear-gradient(180deg, #1A1A2E 0%, #0D0D0D 100%)' }}
      >
        <div className="px-3 py-1.5 border-b border-[#2d5a5a]/30">
          <div className="flex items-center gap-2">
            <span className="text-sm">{getTypeIcon(item.type)}</span>
            <span className="text-sm font-medium truncate" style={{ color: '#C9A962' }}>
              {item.name}
            </span>
          </div>
        </div>
        <button
          onClick={onDiscard}
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-900/20 transition-colors cursor-pointer"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span>丢弃</span>
        </button>
      </div>
    </div>
  );
}

// 确认丢弃对话框
function DiscardConfirmDialog({
  item,
  onConfirm,
  onCancel,
}: {
  item: InventoryItem;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div
        className="relative rounded-xl border border-[#2d5a5a]/50 shadow-2xl shadow-black/50 max-w-sm w-full mx-4 p-5"
        style={{ background: 'linear-gradient(180deg, #1A1A2E 0%, #0D0D0D 100%)' }}
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-full bg-red-500/20 flex items-center justify-center">
            <Trash2 className="w-4 h-4 text-red-400" />
          </div>
          <h3 className="text-base font-semibold" style={{ color: '#C9A962' }}>丢弃物品</h3>
        </div>
        <p className="text-sm leading-relaxed mb-5" style={{ color: '#7F8C8D' }}>
          确定要丢弃 <span style={{ color: '#E8E8E8' }}>{item.name}</span>
          {item.quantity > 1 && <span style={{ color: '#E8E8E8' }}> x{item.quantity}</span>} 吗？
          丢弃后将从储物袋中永久删除。
        </p>
        <div className="flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-1.5 text-sm rounded-lg bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#C9A962] hover:border-[#C9A962]/50 transition-colors cursor-pointer"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-1.5 text-sm text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors shadow-lg shadow-red-500/20 cursor-pointer"
          >
            确认丢弃
          </button>
        </div>
      </div>
    </div>
  );
}

export function BackpackDialog({ open, onClose }: BackpackDialogProps) {
  const { character, deleteInventoryItem } = useGameStore();
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

  // Tooltip 状态
  const [tooltipItem, setTooltipItem] = useState<InventoryItem | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // 上下文菜单状态
  const [contextItem, setContextItem] = useState<InventoryItem | null>(null);
  const [contextPos, setContextPos] = useState({ x: 0, y: 0 });

  // 丢弃确认状态
  const [discardItem, setDiscardItem] = useState<InventoryItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    setTooltipPos({ x: e.clientX, y: e.clientY });
  }, []);

  const handleItemHover = useCallback((item: InventoryItem) => {
    setTooltipItem(item);
  }, []);

  const handleItemLeave = useCallback(() => {
    setTooltipItem(null);
  }, []);

  const handleItemClick = useCallback((item: InventoryItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setTooltipItem(null);
    setContextItem(item);
    setContextPos({ x: e.clientX, y: e.clientY });
  }, []);

  const handleDiscard = useCallback(() => {
    if (contextItem) {
      setDiscardItem(contextItem);
      setContextItem(null);
    }
  }, [contextItem]);

  const confirmDiscard = useCallback(async () => {
    if (!discardItem || isDeleting) return;
    setIsDeleting(true);
    await deleteInventoryItem(discardItem.id);
    setIsDeleting(false);
    setDiscardItem(null);
  }, [discardItem, isDeleting, deleteInventoryItem]);

  // 点击空白处关闭上下文菜单
  useEffect(() => {
    if (!contextItem) return;
    const handler = () => setContextItem(null);
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [contextItem]);

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
          ╔══════════════════════════════════════════════════════════════════════════════════════════════╗
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-0.5 border-b border-[#2d5a5a]/30">
          <div className="flex items-center gap-1.5">
            <span className="text-sm">🎒</span>
            <h2
              className="text-xs font-bold tracking-wider"
              style={{ color: '#C9A962' }}
            >
              储物背包
            </h2>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-5 h-5 rounded bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#C9A962] hover:border-[#C9A962]/50 transition-colors duration-200 cursor-pointer"
          >
            <X className="w-3 h-3" />
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[92vh] overflow-y-auto px-5 py-4">
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
            /* Grouped items in grid */
            <div className="space-y-4">
              {Array.from(groupedItems.entries()).map(([type, items]) => {
                const color = getTypeColor(type);
                return (
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

                    {/* Items grid */}
                    <div className="flex flex-wrap -mr-[5px] -mb-[5px]">
                      {items.map((item) => (
                        <div
                          key={item.id}
                          className={`relative w-8 h-8 rounded border ${color.bg} ${color.border} ${color.hoverBg} flex items-center justify-center cursor-pointer transition-all duration-150 hover:scale-105 mr-[5px] mb-[5px] flex-shrink-0`}
                          onMouseMove={handleMouseMove}
                          onMouseEnter={() => handleItemHover(item)}
                          onMouseLeave={handleItemLeave}
                          onClick={(e) => handleItemClick(item, e)}
                        >
                          <span className="text-xs leading-none">{getTypeIcon(item.type)}</span>
                          {item.quantity > 1 && (
                            <span
                              className="absolute -bottom-0.5 -right-0.5 text-[8px] leading-none font-medium px-0.5 rounded"
                              style={{ color: '#C9A962', background: 'rgba(0,0,0,0.5)' }}
                            >
                              {item.quantity}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
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
          ╚══════════════════════════════════════════════════════════════════════════════════════════════╝
        </div>
      </div>

      {/* Tooltip */}
      {tooltipItem && <ItemTooltip item={tooltipItem} position={tooltipPos} />}

      {/* Context menu */}
      {contextItem && (
        <ContextMenu
          item={contextItem}
          position={contextPos}
          onDiscard={handleDiscard}
          onClose={() => setContextItem(null)}
        />
      )}

      {/* Discard confirm dialog */}
      {discardItem && (
        <DiscardConfirmDialog
          item={discardItem}
          onConfirm={confirmDiscard}
          onCancel={() => setDiscardItem(null)}
        />
      )}
    </div>
  );
}
