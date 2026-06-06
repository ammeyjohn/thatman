import { useGameStore } from '../stores/gameStore';
import { StatusBar } from './StatusBar';
import { Sword, Shield, Circle, Sparkles, MapPin, Activity, TrendingUp, Clock, Shirt, Package } from 'lucide-react';
import type { LayoutSection, LayoutItem, CharacterState } from '../types';

const equipmentIcons: Record<string, React.ReactNode> = {
  sword: <Sword className="w-4 h-4" />,
  shield: <Shield className="w-4 h-4" />,
  circle: <Circle className="w-4 h-4" />,
};

/**
 * 从 character 当前数据中根据 key 路径获取实时值
 * 支持嵌套路径如 "health"、"inventory"
 */
function getLiveValue(character: CharacterState, key: string): unknown {
  // key 到 character 字段的映射
  const keyMap: Record<string, keyof CharacterState> = {
    name: 'name',
    realm: 'realm',
    realm_stage: 'realmStage',
    realmStage: 'realmStage',
    level: 'level',
    health: 'health',
    max_health: 'maxHealth',
    maxHealth: 'maxHealth',
    mana: 'mana',
    max_mana: 'maxMana',
    maxMana: 'maxMana',
    spirit: 'spirit',
    max_spirit: 'maxSpirit',
    maxSpirit: 'maxSpirit',
    spirit_root: 'spiritRoot',
    spiritRoot: 'spiritRoot',
    current_location: 'currentLocation',
    currentLocation: 'currentLocation',
    current_status: 'currentStatus',
    currentStatus: 'currentStatus',
    birth_date: 'birthDate',
    birthDate: 'birthDate',
    lifespan: 'lifespan',
    clothing: 'clothing',
    inventory: 'inventory',
    equipment: 'equipment',
  };
  const field = keyMap[key];
  if (field && character[field] !== undefined && character[field] !== null && character[field] !== '') {
    return character[field];
  }
  return undefined;
}

/**
 * 渲染布局项，优先使用 character 当前数据中的实时值
 */
function renderLayoutItem(item: LayoutItem, liveValue?: unknown) {
  // 优先使用实时值，回退到布局中的快照值
  const value = liveValue !== undefined ? liveValue : item.value;

  switch (item.display_type) {
    case 'bar': {
      const numValue = typeof value === 'number' ? value : parseFloat(String(value)) || 0;
      const maxValue = item.max_value || 100;
      const percentage = Math.min(100, Math.max(0, (numValue / maxValue) * 100));
      return (
        <div key={item.key} className="mb-2">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[#7f8c8d] text-xs">{item.label}</span>
            <span className="text-xs" style={{ color: item.color || '#e8e4dc' }}>
              {numValue}/{maxValue}
            </span>
          </div>
          <div className="w-full h-1.5 bg-[#1a2f2f] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${percentage}%`,
                backgroundColor: item.color || '#4ECDC4',
              }}
            />
          </div>
        </div>
      );
    }
    case 'badge':
      return (
        <span
          key={item.key}
          className="inline-block px-2 py-0.5 rounded text-xs mr-1 mb-1"
          style={{
            backgroundColor: `${item.color || '#c9a227'}20`,
            color: item.color || '#c9a227',
            border: `1px solid ${item.color || '#c9a227'}50`,
          }}
        >
          {item.label}: {String(value)}
        </span>
      );
    case 'list': {
      const listItems = Array.isArray(value) ? value : [value];
      return (
        <div key={item.key} className="mb-1">
          <span className="text-[#7f8c8d] text-xs">{item.label}</span>
          <div className="pl-2 space-y-0.5">
            {listItems.map((li: string | number, idx: number) => (
              <div key={idx} className="text-sm" style={{ color: item.color || '#e8e4dc', fontFamily: 'Noto Serif SC, serif' }}>
                {typeof li === 'object' ? JSON.stringify(li) : li}
              </div>
            ))}
          </div>
        </div>
      );
    }
    case 'text':
    default:
      return (
        <div key={item.key} className="flex justify-between items-center">
          <span className="text-[#7f8c8d] text-xs">{item.label}</span>
          <span className="text-sm" style={{ color: item.color || '#e8e4dc', fontFamily: 'Noto Serif SC, serif' }}>
            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
          </span>
        </div>
      );
  }
}

function renderLayoutSection(section: LayoutSection, character: CharacterState) {
  return (
    <div key={section.id} className="mb-4 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-base">{section.icon}</span>
        <span className="text-xs font-medium" style={{ color: section.title_color || '#c9a227' }}>
          {section.title}
        </span>
      </div>
      <div className="pl-6 space-y-1">
        {section.items.map((item) => {
          const liveValue = getLiveValue(character, item.key);
          return renderLayoutItem(item, liveValue);
        })}
      </div>
    </div>
  );
}

export function CharacterPanel() {
  const { character, characterLayout } = useGameStore();

  return (
    <div className="w-[280px] bg-[#0d1f1f] border-r border-[#2d5a5a]/30 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-[#2d5a5a]/30 bg-[#0d1f1f]">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-[#c9a227]" />
          <h2 className="text-[#e8e4dc] font-bold text-lg" style={{ fontFamily: 'Noto Serif SC, serif' }}>
            角色状态
          </h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {characterLayout ? (
          // 动态布局渲染
          <>
            {/* Avatar & Name - 始终显示 */}
            <div className="text-center mb-6">
              <div className="relative inline-block">
                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-[#2d5a5a] to-[#1a3a3a] border-2 border-[#c9a227] flex items-center justify-center mb-3 shadow-lg shadow-[#c9a227]/20">
                  <span className="text-3xl">👤</span>
                </div>
                <div className="absolute -bottom-1 -right-1 w-6 h-6 bg-[#c9a227] rounded-full flex items-center justify-center">
                  <span className="text-xs">✦</span>
                </div>
              </div>
              <h3 className="text-[#c9a227] font-bold text-xl mb-1" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                {character.name || '未命名'}
              </h3>
            </div>
            {/* 动态布局区块 */}
            {characterLayout.sections.map((section) => renderLayoutSection(section, character))}
          </>
        ) : (
          // 原有硬编码渲染（保持不变）
          <>
            {/* Avatar & Name */}
            <div className="text-center mb-6">
              <div className="relative inline-block">
                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-[#2d5a5a] to-[#1a3a3a] border-2 border-[#c9a227] flex items-center justify-center mb-3 shadow-lg shadow-[#c9a227]/20">
                  <span className="text-3xl">👤</span>
                </div>
                <div className="absolute -bottom-1 -right-1 w-6 h-6 bg-[#c9a227] rounded-full flex items-center justify-center">
                  <span className="text-xs">✦</span>
                </div>
              </div>
              <h3 className="text-[#c9a227] font-bold text-xl mb-1" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                {character.name || '未命名'}
              </h3>
              <div className="flex items-center justify-center gap-2">
                <span className="px-3 py-1 bg-gradient-to-r from-[#c9a227]/20 to-[#c9a227]/10 border border-[#c9a227]/50 rounded-full text-[#c9a227] text-sm font-medium">
                  {character.realm}·{character.realmStage}
                </span>
                {character.level > 0 && (
                  <span className="px-3 py-1 bg-gradient-to-r from-[#5ab8b8]/20 to-[#5ab8b8]/10 border border-[#5ab8b8]/50 rounded-full text-[#5ab8b8] text-sm font-medium flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" />
                    Lv.{character.level}
                  </span>
                )}
              </div>
            </div>

            {/* Current Location */}
            {character.currentLocation && (
              <div className="mb-4 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
                <div className="flex items-center gap-2 mb-1">
                  <MapPin className="w-4 h-4 text-[#5ab8b8]" />
                  <span className="text-[#5ab8b8] text-xs font-medium">当前地点</span>
                </div>
                <p className="text-[#e8e4dc] text-sm pl-6" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                  {character.currentLocation}
                </p>
              </div>
            )}

            {/* Current Status */}
            {character.currentStatus && (
              <div className="mb-4 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
                <div className="flex items-center gap-2 mb-1">
                  <Activity className="w-4 h-4 text-[#8bc34a]" />
                  <span className="text-[#8bc34a] text-xs font-medium">当前状态</span>
                </div>
                <p className="text-[#e8e4dc] text-sm pl-6" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                  {character.currentStatus}
                </p>
              </div>
            )}

            {/* Birth Date & Lifespan */}
            {(character.birthDate || character.lifespan) && (
              <div className="mb-4 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-4 h-4 text-[#c9a227]" />
                  <span className="text-[#c9a227] text-xs font-medium">生辰寿元</span>
                </div>
                <div className="pl-6">
                  {character.birthDate && (
                    <p className="text-[#e8e4dc] text-sm" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                      生于 {character.birthDate}
                    </p>
                  )}
                  {character.lifespan && (
                    <p className="text-[#e8e4dc] text-sm" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                      寿元 {character.lifespan}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Clothing */}
            {character.clothing && (
              <div className="mb-4 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
                <div className="flex items-center gap-2 mb-1">
                  <Shirt className="w-4 h-4 text-[#b388ff]" />
                  <span className="text-[#b388ff] text-xs font-medium">衣着</span>
                </div>
                <p className="text-[#e8e4dc] text-sm pl-6" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                  {character.clothing}
                </p>
              </div>
            )}

            {/* Inventory */}
            {character.inventory && character.inventory.length > 0 && (
              <div className="mb-4 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
                <div className="flex items-center gap-2 mb-1">
                  <Package className="w-4 h-4 text-[#ffab40]" />
                  <span className="text-[#ffab40] text-xs font-medium">随身物品</span>
                </div>
                <div className="pl-6 space-y-1">
                  {character.inventory.map((item) => (
                    <div key={item.id} className="flex items-center justify-between">
                      <span className="text-[#e8e4dc] text-sm" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                        {item.name}
                      </span>
                      {item.quantity > 1 && (
                        <span className="text-[#5a7a7a] text-xs">x{item.quantity}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
