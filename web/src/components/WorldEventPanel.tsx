import React, { useState } from 'react';
import { useGameStore } from '../stores/gameStore';
import { MapPin, Clock, Users } from 'lucide-react';
import { CharacterList } from './CharacterList';

type TabType = 'events' | 'characters';

export function WorldEventPanel() {
  const { world, worldLayout } = useGameStore();
  const layoutRef = React.useRef<HTMLDivElement>(null);
  const scriptsRef = React.useRef<string[]>([]);
  const [activeTab, setActiveTab] = useState<TabType>('events');

  // 注入实时数据并执行布局中的脚本
  React.useEffect(() => {
    if (!worldLayout || !layoutRef.current) return;

    const container = layoutRef.current;

    // 提取并缓存脚本内容（布局变化时）
    const scripts = container.querySelectorAll('script');
    if (scripts.length > 0) {
      scriptsRef.current = Array.from(scripts).map(s => s.textContent || '');
      scripts.forEach(s => s.remove());
    }

    // 设置数据上下文并执行脚本
    (window as any).__LAYOUT_DATA__ = world;
    scriptsRef.current.forEach(content => {
      const script = document.createElement('script');
      script.textContent = content;
      container.appendChild(script);
      script.remove();
    });
  }, [world, worldLayout]);

  return (
    <div className="w-[280px] h-full bg-[#0d1f1f] border-l border-[#2d5a5a]/30 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[#2d5a5a]/30 bg-[#0d1f1f]">
        <div className="flex items-center gap-2">
          <MapPin className="w-5 h-5 text-[#c9a227]" />
          <h2 className="text-[#e8e4dc] font-bold text-lg" style={{ fontFamily: 'Noto Serif SC, serif' }}>
            世界
          </h2>
        </div>
      </div>

      {/* Tab 切换栏 */}
      <div className="flex border-b border-[#2d5a5a]/30">
        <button
          onClick={() => setActiveTab('events')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium transition-all duration-200 ${
            activeTab === 'events'
              ? 'text-[#c9a227] border-b-2 border-[#c9a227]'
              : 'text-[#7ababa] hover:text-[#a0d0d0] border-b-2 border-transparent'
          }`}
          style={{ fontFamily: 'Noto Serif SC, serif' }}
        >
          <MapPin className="w-3.5 h-3.5" />
          <span>世界事件</span>
        </button>
        <button
          onClick={() => setActiveTab('characters')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium transition-all duration-200 ${
            activeTab === 'characters'
              ? 'text-[#c9a227] border-b-2 border-[#c9a227]'
              : 'text-[#7ababa] hover:text-[#a0d0d0] border-b-2 border-transparent'
          }`}
          style={{ fontFamily: 'Noto Serif SC, serif' }}
        >
          <Users className="w-3.5 h-3.5" />
          <span>人物</span>
        </button>
      </div>

      {/* Tab 内容区 */}
      {activeTab === 'events' ? (
        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-4 scrollbar-thin">
          {/* Game Date — 始终显示在顶部 */}
          {world.gameDate && (
            <div className="mb-4 p-3 bg-gradient-to-r from-[#c9a227]/10 to-transparent rounded-lg border border-[#c9a227]/30">
              <div className="flex items-center gap-2 text-[#c9a227]">
                <span className="text-sm font-medium" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                  {world.gameDate}
                </span>
              </div>
            </div>
          )}

          {/* Shichen (Time Period) — 始终显示 */}
          {(world.time || world.timePeriod) && (
            <div className="mb-4 p-3 bg-gradient-to-r from-[#3d6a6a]/20 to-transparent rounded-lg border border-[#3d6a6a]/30">
              <div className="flex items-center gap-2 text-[#7ababa]">
                <Clock className="w-4 h-4" />
                <span className="text-sm font-medium">
                  {world.time}{world.timePeriod ? ` · ${world.timePeriod}` : ''}
                </span>
              </div>
            </div>
          )}

          {worldLayout ? (
            // 动态 HTML 布局渲染
            <div ref={layoutRef} dangerouslySetInnerHTML={{ __html: worldLayout }} />
          ) : (
            // 原有硬编码渲染（无布局时的回退）
            <>
              {/* Weather & Spirit Tide */}
              {(world.weather || world.spiritTide) && (
                <div className="mb-4 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[#c9a227] text-xs font-medium">天象灵气</span>
                  </div>
                  <div className="pl-0 space-y-1">
                    {world.weather && (
                      <p className="text-[#e8e4dc] text-sm" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                        {world.weather}{world.weatherDesc ? ` · ${world.weatherDesc}` : ''}
                      </p>
                    )}
                    {world.spiritTide && (
                      <p className="text-[#4ECDC4] text-sm" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                        灵潮涌动 {world.spiritTideIntensity ? `· 强度${world.spiritTideIntensity}` : ''}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Events */}
              {world.events && world.events.length > 0 && (
                <div className="mb-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[#c9a227] text-xs font-medium">当下事件</span>
                  </div>
                  <div className="space-y-2">
                    {world.events.map((event) => (
                      <div key={event.id} className="p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`w-2 h-2 rounded-full ${
                            event.type === 'urgent' ? 'bg-[#E74C3C]' :
                            event.type === 'important' ? 'bg-[#c9a227]' :
                            'bg-[#5ab8b8]'
                          }`} />
                          <span className="text-[#e8e4dc] text-sm font-medium" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                            {event.title}
                          </span>
                        </div>
                        {event.description && (
                          <p className="text-[#7F8C8D] text-xs pl-4" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                            {event.description}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden scrollbar-thin">
          <CharacterList />
        </div>
      )}
    </div>
  );
}
