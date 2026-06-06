import { useGameStore } from '../stores/gameStore';
import { useChatStore } from '../stores/chatStore';
import { MapPin, Clock } from 'lucide-react';

export function WorldEventPanel() {
  const { world } = useGameStore();
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
        {/* Time */}
        <div className="mb-4 p-3 bg-gradient-to-r from-[#3d6a6a]/20 to-transparent rounded-lg border border-[#3d6a6a]/30">
          <div className="flex items-center gap-2 text-[#7ababa]">
            <Clock className="w-4 h-4" />
            <span className="text-sm font-medium">{displayTime}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
