import { useState } from 'react';
import { X, Store, Minus, Plus, Trash2 } from 'lucide-react';
import { useGameStore } from '../stores/gameStore';
import type { InventoryItem } from '../types';

interface StallDialogProps {
  open: boolean;
  onClose: () => void;
}

interface StallItemInput {
  item_id: string;
  name: string;
  type: string;
  description: string;
  quantity: number;
  price?: number;
}

export function StallDialog({ open, onClose }: StallDialogProps) {
  const { character, myStall, createStall, closeMyStall } = useGameStore();
  const [stallName, setStallName] = useState('');
  const [selectedItems, setSelectedItems] = useState<Map<string, StallItemInput>>(new Map());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  if (!open) return null;

  const inventory = character.inventory || [];

  const isStallOpen = myStall && myStall.status === 'open';

  const toggleItem = (item: InventoryItem) => {
    setSelectedItems(prev => {
      const next = new Map(prev);
      if (next.has(item.id)) {
        next.delete(item.id);
      } else {
        next.set(item.id, {
          item_id: item.id,
          name: item.name,
          type: item.type,
          description: item.description,
          quantity: 1,
        });
      }
      return next;
    });
  };

  const updateQuantity = (itemId: string, delta: number, maxQty: number) => {
    setSelectedItems(prev => {
      const next = new Map(prev);
      const item = next.get(itemId);
      if (item) {
        item.quantity = Math.max(1, Math.min(maxQty, item.quantity + delta));
        next.set(itemId, { ...item });
      }
      return next;
    });
  };

  const updatePrice = (itemId: string, price: string) => {
    setSelectedItems(prev => {
      const next = new Map(prev);
      const item = next.get(itemId);
      if (item) {
        const priceNum = parseInt(price);
        if (!isNaN(priceNum) && priceNum > 0) {
          next.set(itemId, { ...item, price: priceNum });
        } else if (price === '') {
          const updated = { ...item };
          delete updated.price;
          next.set(itemId, updated);
        }
      }
      return next;
    });
  };

  const handleCreateStall = async () => {
    if (!stallName.trim()) {
      setMessage('请输入摊位名称');
      setTimeout(() => setMessage(''), 3000);
      return;
    }
    if (selectedItems.size === 0) {
      setMessage('请至少选择一件物品上架');
      setTimeout(() => setMessage(''), 3000);
      return;
    }

    setLoading(true);
    setMessage('');
    const items = Array.from(selectedItems.values());
    await createStall(stallName, items);
    setLoading(false);
    setMessage('摊位已开设');
    setTimeout(() => {
      setMessage('');
    }, 2000);
  };

  const handleCloseStall = async () => {
    setLoading(true);
    setMessage('');
    await closeMyStall();
    setLoading(false);
    setMessage('摊位已关闭，物品已归还背包');
    setTimeout(() => {
      setMessage('');
      onClose();
    }, 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      {/* Dialog */}
      <div
        className="relative w-full max-w-lg mx-4 rounded-xl border border-[#2d5a5a]/50 shadow-2xl shadow-black/50 overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, #1A1A2E 0%, #0D0D0D 100%)',
          fontFamily: 'Noto Serif SC, serif',
        }}
      >
        {/* Top border */}
        <div className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden" style={{ fontFamily: 'monospace' }}>
          ╔══════════════════════════════════════════════════════════════╗
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#2d5a5a]/30">
          <div className="flex items-center gap-2">
            <span className="text-xl">🏪</span>
            <h2 className="text-lg font-bold tracking-wider" style={{ color: '#C9A962' }}>
              {isStallOpen ? '我的摊位' : '开设摊位'}
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
          {isStallOpen ? (
            /* 已有摊位 - 显示摊位信息 */
            <div className="space-y-3">
              <div className="p-3 bg-[#4ECDC4]/10 rounded-lg border border-[#4ECDC4]/30">
                <div className="flex items-center gap-2 mb-1">
                  <Store className="w-4 h-4 text-[#4ECDC4]" />
                  <span className="text-sm text-[#4ECDC4] font-medium">{myStall!.stallName}</span>
                </div>
                <p className="text-xs text-[#7F8C8D]">位置: {myStall!.location}</p>
                <p className="text-xs text-[#7F8C8D]">在售物品: {myStall!.items.length} 种</p>
              </div>

              {myStall!.items.map((item) => (
                <div key={item.itemId} className="flex items-center justify-between p-2 bg-[#1a2f2f]/30 rounded-lg">
                  <div>
                    <span className="text-sm text-[#e8e4dc]">{item.name}</span>
                    <span className="text-xs text-[#7F8C8D] ml-2">×{item.quantity}</span>
                  </div>
                  <span className="text-xs text-[#4ECDC4]">{item.price} 灵石/个</span>
                </div>
              ))}

              <button
                onClick={handleCloseStall}
                disabled={loading}
                className="w-full py-2.5 mt-2 text-sm rounded-lg bg-[#E74C3C]/20 text-[#E74C3C] border border-[#E74C3C]/30 hover:bg-[#E74C3C]/30 transition-colors duration-200 cursor-pointer disabled:opacity-50"
              >
                关闭摊位（物品归还背包）
              </button>
            </div>
          ) : (
            /* 开设摊位 */
            <div className="space-y-4">
              {/* 摊位名称 */}
              <div>
                <label className="text-xs text-[#7F8C8D] mb-1 block">摊位名称</label>
                <input
                  type="text"
                  value={stallName}
                  onChange={(e) => setStallName(e.target.value)}
                  placeholder="给你的摊位取个名字"
                  className="w-full px-3 py-2 bg-[#1a2f2f]/50 border border-[#2d5a5a]/30 rounded-lg text-sm text-[#e8e4dc] placeholder-[#5a7a7a] focus:border-[#4ECDC4]/50 focus:outline-none transition-colors duration-200"
                  style={{ fontFamily: 'Noto Serif SC, serif' }}
                />
              </div>

              {/* 选择物品 */}
              <div>
                <label className="text-xs text-[#7F8C8D] mb-2 block">选择上架物品</label>
                {inventory.length === 0 ? (
                  <p className="text-xs text-[#5a7a7a] py-4 text-center">背包中没有物品</p>
                ) : (
                  <div className="space-y-2">
                    {inventory.map((item) => {
                      const isSelected = selectedItems.has(item.id);
                      const selectedItem = selectedItems.get(item.id);
                      return (
                        <div
                          key={item.id}
                          className={`p-3 rounded-lg border transition-colors duration-200 ${
                            isSelected
                              ? 'bg-[#4ECDC4]/10 border-[#4ECDC4]/30'
                              : 'bg-[#1a2f2f]/30 border-[#2d5a5a]/20 hover:border-[#2d5a5a]/50'
                          }`}
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleItem(item)}
                              className="w-4 h-4 rounded border-[#2d5a5a] accent-[#4ECDC4] cursor-pointer"
                            />
                            <span className="text-sm text-[#e8e4dc] flex-1">{item.name}</span>
                            <span className="text-xs text-[#7F8C8D]">库存: {item.quantity}</span>
                          </div>
                          {isSelected && selectedItem && (
                            <div className="flex items-center gap-3 mt-2 pl-6">
                              <span className="text-xs text-[#7F8C8D]">数量:</span>
                              <button onClick={() => updateQuantity(item.id, -1, item.quantity)} className="w-5 h-5 flex items-center justify-center rounded bg-[#2d5a5a]/30 text-[#7ababa] cursor-pointer">
                                <Minus className="w-3 h-3" />
                              </button>
                              <span className="text-xs text-[#e8e4dc] w-4 text-center">{selectedItem.quantity}</span>
                              <button onClick={() => updateQuantity(item.id, 1, item.quantity)} className="w-5 h-5 flex items-center justify-center rounded bg-[#2d5a5a]/30 text-[#7ababa] cursor-pointer">
                                <Plus className="w-3 h-3" />
                              </button>
                              <span className="text-xs text-[#7F8C8D] ml-2">单价:</span>
                              <input
                                type="number"
                                min="1"
                                value={selectedItem.price ?? ''}
                                onChange={(e) => updatePrice(item.id, e.target.value)}
                                placeholder="均价"
                                className="w-16 px-2 py-1 bg-[#0d1f1f] border border-[#2d5a5a]/30 rounded text-xs text-[#e8e4dc] placeholder-[#5a7a7a] focus:border-[#4ECDC4]/50 focus:outline-none"
                              />
                              <span className="text-[10px] text-[#5a7a7a]">灵石(空=均价)</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* 开摊按钮 */}
              <button
                onClick={handleCreateStall}
                disabled={loading || selectedItems.size === 0}
                className="w-full py-2.5 text-sm rounded-lg bg-[#4ECDC4]/20 text-[#4ECDC4] border border-[#4ECDC4]/30 hover:bg-[#4ECDC4]/30 transition-colors duration-200 cursor-pointer disabled:opacity-50"
              >
                {loading ? '开设中...' : `开设摊位 (${selectedItems.size} 件物品)`}
              </button>
            </div>
          )}
        </div>

        {/* Message */}
        {message && (
          <div className="px-5 py-2 text-center">
            <span className="text-xs text-[#4ECDC4]">{message}</span>
          </div>
        )}

        {/* Bottom border */}
        <div className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden" style={{ fontFamily: 'monospace' }}>
          ╚══════════════════════════════════════════════════════════════╝
        </div>
      </div>
    </div>
  );
}
