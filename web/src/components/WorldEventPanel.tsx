import { useGameStore } from '../stores/gameStore';
import { useChatStore } from '../stores/chatStore';
import { MapPin, Clock } from 'lucide-react';
import type { LayoutSection, LayoutItem, WorldState } from '../types';

/**
 * 从 world 当前数据中根据 key 获取实时值
 */
function getLiveValue(world: WorldState, key: string): unknown {
  const keyMap: Record<string, keyof WorldState> = {
    time: 'time',
    time_period: 'timePeriod',
    timePeriod: 'timePeriod',
    weather: 'weather',
    weather_desc: 'weatherDesc',
    weatherDesc: 'weatherDesc',
    spirit_tide: 'spiritTide',
    spiritTide: 'spiritTide',
    spirit_tide_intensity: 'spiritTideIntensity',
    spiritTideIntensity: 'spiritTideIntensity',
    location: 'location',
    events: 'events',
  };
  const field = keyMap[key];
  if (field && world[field] !== undefined && world[field] !== null && world[field] !== '') {
    return world[field];
  }
  return undefined;
}

/**
 * 渲染布局项，优先使用 world 当前数据中的实时值
 */
function renderLayoutItem(item: LayoutItem, liveValue?: unknown) {
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
                {typeof li === 'object' ? JSON.stringify(li) : String(li)}
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

function renderLayoutSection(section: LayoutSection, world: WorldState) {
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
          const liveValue = getLiveValue(world, item.key);
          return renderLayoutItem(item, liveValue);
        })}
      </div>
    </div>
  );
}

export function WorldEventPanel() {
  const { world, worldLayout } = useGameStore();
  const { lastTime } = useChatStore();

  // 优先使用从后端 JSON 解析出的 location/time，否则回退到 gameStore 的默认值
  const displayTime = lastTime || world.time;

  return (
    <div className="w-[280px] bg-[#0d1f1f] border-l border-[#2d5a5a]/30 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-[#2d5a5a]/30 bg-[#0d1f1f]">
        <div className="flex items-center gap-2">
          <MapPin className="w-5 h-5 text-[#c9a227]" />
          <h2 className="text-[#e8e4dc] font-bold text-lg" style={{ fontFamily: 'Noto Serif SC, serif' }}>
            世界事件
          </h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {worldLayout ? (
          // 动态布局渲染
          worldLayout.sections.map((section) => renderLayoutSection(section, world))
        ) : (
          // 原有硬编码渲染
          <>
            {/* Time */}
            <div className="mb-4 p-3 bg-gradient-to-r from-[#3d6a6a]/20 to-transparent rounded-lg border border-[#3d6a6a]/30">
              <div className="flex items-center gap-2 text-[#7ababa]">
                <Clock className="w-4 h-4" />
                <span className="text-sm font-medium">{displayTime}</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
