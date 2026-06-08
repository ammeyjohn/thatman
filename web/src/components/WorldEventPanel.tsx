import React from 'react';
import { useGameStore } from '../stores/gameStore';
import { useChatStore } from '../stores/chatStore';
import { MapPin, Clock } from 'lucide-react';

export function WorldEventPanel() {
  const { world, worldLayout } = useGameStore();
  const { lastTime } = useChatStore();
  const layoutRef = React.useRef<HTMLDivElement>(null);
  const scriptsRef = React.useRef<string[]>([]);

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
          // 动态 HTML 布局渲染
          <div ref={layoutRef} dangerouslySetInnerHTML={{ __html: worldLayout }} />
        ) : (
          // 原有硬编码渲染
          <>
            {/* Location */}
            {world.location && (
              <div className="mb-4 p-3 bg-gradient-to-r from-[#3d6a6a]/20 to-transparent rounded-lg border border-[#3d6a6a]/30">
                <div className="flex items-center gap-2 text-[#5ab8b8]">
                  <MapPin className="w-4 h-4" />
                  <span className="text-sm font-medium" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                    {world.location}
                  </span>
                </div>
              </div>
            )}

            {/* Time */}
            {(displayTime || world.timePeriod) && (
              <div className="mb-4 p-3 bg-gradient-to-r from-[#3d6a6a]/20 to-transparent rounded-lg border border-[#3d6a6a]/30">
                <div className="flex items-center gap-2 text-[#7ababa]">
                  <Clock className="w-4 h-4" />
                  <span className="text-sm font-medium">
                    {displayTime}{world.timePeriod ? ` · ${world.timePeriod}` : ''}
                  </span>
                </div>
              </div>
            )}

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
    </div>
  );
}
