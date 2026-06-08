import { X } from 'lucide-react';
import { useGameStore } from '../stores/gameStore';
import type { Equipment } from '../types';

interface EquipmentDialogProps {
  open: boolean;
  onClose: () => void;
}

interface SlotConfig {
  key: string;
  label: string;
  icon: string;
  type: 'weapon' | 'armor' | 'accessory' | 'clothing';
}

const SLOTS: SlotConfig[] = [
  { key: 'weapon', label: '武器', icon: '🗡️', type: 'weapon' },
  { key: 'armor', label: '防具', icon: '🛡️', type: 'armor' },
  { key: 'accessory', label: '饰品', icon: '💍', type: 'accessory' },
  { key: 'clothing', label: '衣着', icon: '👘', type: 'clothing' },
];

function getEquipmentDescription(item: Equipment): string | undefined {
  return (item as Equipment & { description?: string }).description;
}

export function EquipmentDialog({ open, onClose }: EquipmentDialogProps) {
  const { character } = useGameStore();
  const equipment = character.equipment ?? [];
  const clothing = character.clothing ?? '';

  const isEmpty = equipment.length === 0 && !clothing;

  function findEquipment(type: 'weapon' | 'armor' | 'accessory'): Equipment | undefined {
    return equipment.find((item) => item.type === type);
  }

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
            <span className="text-xl">🛡️</span>
            <h2
              className="text-lg font-bold tracking-wider"
              style={{ color: '#C9A962' }}
            >
              角色装备
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
              <span className="text-5xl mb-4 opacity-40">🛡️</span>
              <p className="text-[#7F8C8D] text-base" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                暂无装备
              </p>
              <p className="text-[#7F8C8D]/60 text-xs mt-2" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                闯荡修仙世界，寻觅神兵利器
              </p>
            </div>
          ) : (
            /* Equipment slots */
            <div className="space-y-4">
              {SLOTS.map((slot) => {
                const item = slot.type === 'clothing'
                  ? undefined
                  : findEquipment(slot.type);
                const isClothingSlot = slot.type === 'clothing';
                const hasItem = isClothingSlot ? !!clothing : !!item;
                const description = item ? getEquipmentDescription(item) : undefined;

                return (
                  <div key={slot.key}>
                    {/* Slot label */}
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-base">{slot.icon}</span>
                      <span
                        className="text-sm font-medium tracking-wide"
                        style={{ color: '#4ECDC4' }}
                      >
                        {slot.label}
                      </span>
                    </div>

                    {/* Section separator */}
                    <div
                      className="text-[#2d5a5a]/50 text-[10px] leading-none mb-2 select-none overflow-hidden whitespace-nowrap"
                      style={{ fontFamily: 'monospace' }}
                    >
                      ◈ ───────────────────────────────────────────────────────── ◈
                    </div>

                    {/* Slot content */}
                    <div className="px-3 py-2.5">
                      {hasItem ? (
                        <div>
                          <span
                            className="text-sm font-medium"
                            style={{ color: '#E8E8E8' }}
                          >
                            {isClothingSlot ? clothing : item!.name}
                          </span>
                          {description && (
                            <p
                              className="text-xs mt-1 leading-relaxed"
                              style={{ color: '#7F8C8D' }}
                            >
                              {description}
                            </p>
                          )}
                        </div>
                      ) : (
                        <span
                          className="text-sm italic"
                          style={{ color: '#7F8C8D' }}
                        >
                          未装备
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

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
