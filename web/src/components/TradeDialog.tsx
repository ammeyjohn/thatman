import { useState, useEffect } from 'react';
import { X, ShoppingBag, Gem, Minus, Plus } from 'lucide-react';
import { useGameStore } from '../stores/gameStore';
import type { Stall, StallItem, InventoryItem } from '../types';

interface TradeDialogProps {
  open: boolean;
  onClose: () => void;
  stallId: string;
  ownerName: string;
}

type TradeTab = 'buy' | 'sell';

export function TradeDialog({ open, onClose, stallId, ownerName }: TradeDialogProps) {
  const { nearbyStalls, character, buyFromStall, sellToStall, fetchNearbyStalls } = useGameStore();
  const [activeTab, setActiveTab] = useState<TradeTab>('buy');
  const [stall, setStall] = useState<Stall | null>(null);
  const [buyQuantities, setBuyQuantities] = useState<Record<string, number>>({});
  const [sellQuantities, setSellQuantities] = useState<Record<string, number>>({});
  const [sellPrices, setSellPrices] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  // 加载摊位数据
  useEffect(() => {
    if (!open) return;
    const found = nearbyStalls.find(s => s.stallId === stallId);
    if (found) {
      setStall(found);
    } else {
      // 尝试从API获取
      fetchNearbyStalls();
    }
  }, [open, stallId, nearbyStalls, fetchNearbyStalls]);

  // 更新摊位数据
  useEffect(() => {
    const found = nearbyStalls.find(s => s.stallId === stallId);
    if (found) setStall(found);
  }, [nearbyStalls, stallId]);

  if (!open || !stall) return null;

  const spiritStones = character.spiritStones || { low: 0, medium: 0, high: 0, top: 0 };
  const totalLowStones = spiritStones.low + spiritStones.medium * 10 + spiritStones.high * 100 + spiritStones.top * 1000;

  const handleBuy = async (item: StallItem) => {
    const qty = buyQuantities[item.itemId] || 1;
    setLoading(true);
    setMessage('');
    await buyFromStall(stallId, item.itemId, qty);
    setLoading(false);
    setMessage(`购买了 ${item.name} ×${qty}`);
    setBuyQuantities(prev => ({ ...prev, [item.itemId]: 1 }));
    setTimeout(() => setMessage(''), 3000);
  };

  const handleSell = async (item: InventoryItem) => {
    const qty = sellQuantities[item.id] || 1;
    const price = sellPrices[item.id];
    setLoading(true);
    setMessage('');
    await sellToStall(stallId, item.id, qty, price);
    setLoading(false);
    setMessage(`出售了 ${item.name} ×${qty}`);
    setSellQuantities(prev => ({ ...prev, [item.id]: 1 }));
    setTimeout(() => setMessage(''), 3000);
  };

  const updateBuyQty = (itemId: string, delta: number) => {
    setBuyQuantities(prev => {
      const current = prev[itemId] || 1;
      return { ...prev, [itemId]: Math.max(1, current + delta) };
    });
  };

  const updateSellQty = (itemId: string, delta: number, maxQty: number) => {
    setSellQuantities(prev => {
      const current = prev[itemId] || 1;
      return { ...prev, [itemId]: Math.max(1, Math.min(maxQty, current + delta)) };
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      {/* Dialog */}
      <div
        className="relative w-full max-w-2xl mx-4 rounded-xl border border-[#2d5a5a]/50 shadow-2xl shadow-black/50 overflow-hidden"
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
              {stall.stallName || `${ownerName}的摊位`}
            </h2>
            <span className="text-xs text-[#7F8C8D]">摊主: {ownerName}</span>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-md bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#C9A962] hover:border-[#C9A962]/50 transition-colors duration-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Spirit Stones Display */}
        <div className="px-5 py-2 border-b border-[#2d5a5a]/20 bg-[#0D0D0D]/50">
          <div className="flex items-center gap-3">
            <Gem className="w-4 h-4 text-[#4ECDC4]" />
            <span className="text-xs text-[#7F8C8D]">灵石余额:</span>
            <span className="text-xs text-[#e8e4dc]">{spiritStones.low} 下品</span>
            {spiritStones.medium > 0 && <span className="text-xs text-[#5ab8b8]">{spiritStones.medium} 中品</span>}
            {spiritStones.high > 0 && <span className="text-xs text-[#c9a227]">{spiritStones.high} 上品</span>}
            {spiritStones.top > 0 && <span className="text-xs text-[#E74C3C]">{spiritStones.top} 极品</span>}
            <span className="text-[10px] text-[#5a7a7a]">(≈{totalLowStones} 下品)</span>
          </div>
        </div>

        {/* Tab */}
        <div className="flex border-b border-[#2d5a5a]/30">
          <button
            onClick={() => setActiveTab('buy')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium transition-all duration-200 cursor-pointer ${
              activeTab === 'buy' ? 'text-[#4ECDC4] border-b-2 border-[#4ECDC4]' : 'text-[#7ababa] hover:text-[#a0d0d0] border-b-2 border-transparent'
            }`}
          >
            <ShoppingBag className="w-3.5 h-3.5" />
            <span>购买</span>
          </button>
          <button
            onClick={() => setActiveTab('sell')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium transition-all duration-200 cursor-pointer ${
              activeTab === 'sell' ? 'text-[#c9a227] border-b-2 border-[#c9a227]' : 'text-[#7ababa] hover:text-[#a0d0d0] border-b-2 border-transparent'
            }`}
          >
            <span>出售</span>
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[50vh] overflow-y-auto px-5 py-4">
          {activeTab === 'buy' ? (
            /* Buy tab */
            stall.items.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8">
                <span className="text-4xl mb-3 opacity-40">📦</span>
                <p className="text-[#7F8C8D] text-sm">摊位上暂无物品</p>
              </div>
            ) : (
              <div className="space-y-2">
                {stall.items.map((item) => (
                  <div key={item.itemId} className="flex items-center gap-3 p-3 bg-[#1a2f2f]/30 rounded-lg border border-[#2d5a5a]/20 hover:border-[#4ECDC4]/30 transition-colors duration-200">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-[#e8e4dc] font-medium">{item.name}</span>
                        {item.grade && <span className="text-[10px] px-1 py-0.5 rounded bg-[#c9a227]/20 text-[#c9a227]">{item.grade}</span>}
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs text-[#7F8C8D]">库存: {item.quantity}</span>
                        <span className="text-xs text-[#4ECDC4]">{item.price} 灵石/个</span>
                      </div>
                      {item.description && <p className="text-[10px] text-[#5a7a7a] mt-0.5">{item.description}</p>}
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => updateBuyQty(item.itemId, -1)} className="w-6 h-6 flex items-center justify-center rounded bg-[#2d5a5a]/30 text-[#7ababa] hover:text-[#4ECDC4] cursor-pointer">
                        <Minus className="w-3 h-3" />
                      </button>
                      <span className="text-sm text-[#e8e4dc] w-6 text-center">{buyQuantities[item.itemId] || 1}</span>
                      <button onClick={() => updateBuyQty(item.itemId, 1)} className="w-6 h-6 flex items-center justify-center rounded bg-[#2d5a5a]/30 text-[#7ababa] hover:text-[#4ECDC4] cursor-pointer">
                        <Plus className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => handleBuy(item)}
                        disabled={loading}
                        className="px-3 py-1.5 text-xs rounded bg-[#4ECDC4]/20 text-[#4ECDC4] border border-[#4ECDC4]/30 hover:bg-[#4ECDC4]/30 transition-colors duration-200 cursor-pointer disabled:opacity-50"
                      >
                        购买
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            /* Sell tab */
            character.inventory.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8">
                <span className="text-4xl mb-3 opacity-40">🎒</span>
                <p className="text-[#7F8C8D] text-sm">背包中没有可出售的物品</p>
              </div>
            ) : (
              <div className="space-y-2">
                {character.inventory.map((item) => (
                  <div key={item.id} className="flex items-center gap-3 p-3 bg-[#1a2f2f]/30 rounded-lg border border-[#2d5a5a]/20 hover:border-[#c9a227]/30 transition-colors duration-200">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-[#e8e4dc] font-medium">{item.name}</span>
                        {item.type && <span className="text-[10px] px-1 py-0.5 rounded bg-[#5ab8b8]/20 text-[#5ab8b8]">{item.type}</span>}
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs text-[#7F8C8D]">持有: {item.quantity}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => updateSellQty(item.id, -1, item.quantity)} className="w-6 h-6 flex items-center justify-center rounded bg-[#2d5a5a]/30 text-[#7ababa] hover:text-[#c9a227] cursor-pointer">
                        <Minus className="w-3 h-3" />
                      </button>
                      <span className="text-sm text-[#e8e4dc] w-6 text-center">{sellQuantities[item.id] || 1}</span>
                      <button onClick={() => updateSellQty(item.id, 1, item.quantity)} className="w-6 h-6 flex items-center justify-center rounded bg-[#2d5a5a]/30 text-[#7ababa] hover:text-[#c9a227] cursor-pointer">
                        <Plus className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => handleSell(item)}
                        disabled={loading}
                        className="px-3 py-1.5 text-xs rounded bg-[#c9a227]/20 text-[#c9a227] border border-[#c9a227]/30 hover:bg-[#c9a227]/30 transition-colors duration-200 cursor-pointer disabled:opacity-50"
                      >
                        出售
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
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
