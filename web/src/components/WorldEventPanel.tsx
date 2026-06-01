import { useGameStore } from '../stores/gameStore';
import { Clock, Cloud, Waves, MapPin, Bell } from 'lucide-react';

export function WorldEventPanel() {
  const { world } = useGameStore();

  const getEventTypeColor = (type: string) => {
    switch (type) {
      case 'urgent':
        return 'border-[#c94e4e]/50 bg-[#c94e4e]/10';
      case 'important':
        return 'border-[#c9a227]/50 bg-[#c9a227]/10';
      default:
        return 'border-[#2d5a5a]/30 bg-[#1a2f2f]/30';
    }
  };

  const getEventTypeIcon = (type: string) => {
    switch (type) {
      case 'urgent':
        return '🔥';
      case 'important':
        return '✨';
      default:
        return '📜';
    }
  };

  return (
    <div className="w-[280px] bg-gradient-to-b from-[#0d1f1f] to-[#0a1515] border-l border-[#2d5a5a]/30 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-[#2d5a5a]/30">
        <div className="flex items-center gap-2">
          <MapPin className="w-5 h-5 text-[#c9a227]" />
          <h2 className="text-[#e8e4dc] font-bold text-lg" style={{ fontFamily: 'Noto Serif SC, serif' }}>
            世界事件
          </h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {/* Location */}
        <div className="mb-4 p-3 bg-gradient-to-r from-[#2d5a5a]/20 to-transparent rounded-lg border border-[#2d5a5a]/30">
          <div className="flex items-center gap-2 text-[#c9a227]">
            <MapPin className="w-4 h-4" />
            <span className="text-sm font-medium">{world.location}</span>
          </div>
        </div>

        {/* Time & Weather */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-4 h-4 text-[#3d9a9a]" />
              <span className="text-xs text-[#a0c0c0]">时辰</span>
            </div>
            <div className="text-[#e8e4dc] font-medium">{world.time}</div>
            <div className="text-xs text-[#a0c0c0]">{world.timePeriod}</div>
          </div>
          <div className="p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
            <div className="flex items-center gap-2 mb-2">
              <Cloud className="w-4 h-4 text-[#3d9a9a]" />
              <span className="text-xs text-[#a0c0c0]">天气</span>
            </div>
            <div className="text-[#e8e4dc] font-medium">{world.weather}</div>
            <div className="text-xs text-[#a0c0c0]">{world.weatherDesc}</div>
          </div>
        </div>

        {/* Spirit Tide */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Waves className="w-4 h-4 text-[#c9a227]" />
            <span className="text-sm text-[#a0c0c0]">灵潮状态</span>
          </div>
          <div
            className={`p-3 rounded-lg border transition-all duration-500 ${
              world.spiritTide
                ? 'border-[#c9a227]/50 bg-gradient-to-r from-[#c9a227]/20 to-[#c9a227]/5 shadow-lg shadow-[#c9a227]/10'
                : 'border-[#2d5a5a]/30 bg-[#1a2f2f]/30'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={world.spiritTide ? 'text-[#c9a227] font-medium' : 'text-[#a0c0c0]'}>
                {world.spiritTide ? '✦ 灵潮涌动' : '○ 灵气平稳'}
              </span>
              {world.spiritTide && (
                <span className="text-xs text-[#c9a227]">+{world.spiritTideIntensity}0% 灵气</span>
              )}
            </div>
            {world.spiritTide && (
              <div className="mt-2 h-1 bg-[#1a2f2f] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#c9a227] to-[#f0d878] rounded-full animate-pulse"
                  style={{ width: `${world.spiritTideIntensity * 33}%` }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Events */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Bell className="w-4 h-4 text-[#3d9a9a]" />
            <span className="text-sm text-[#a0c0c0]">世界动态</span>
          </div>
          <div className="space-y-2">
            {world.events.map((event) => (
              <div
                key={event.id}
                className={`p-3 rounded-lg border ${getEventTypeColor(event.type)} hover:border-[#3d7a7a]/50 transition-colors cursor-pointer`}
              >
                <div className="flex items-start gap-2">
                  <span className="text-lg">{getEventTypeIcon(event.type)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[#e8e4dc] text-sm font-medium mb-1">{event.title}</div>
                    <div className="text-[#a0c0c0] text-xs leading-relaxed">{event.description}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
