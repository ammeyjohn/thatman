import { useGameStore } from '../stores/gameStore';
import { StatusBar } from './StatusBar';
import { Sword, Shield, Circle, Sparkles } from 'lucide-react';

const equipmentIcons: Record<string, React.ReactNode> = {
  sword: <Sword className="w-4 h-4" />,
  shield: <Shield className="w-4 h-4" />,
  circle: <Circle className="w-4 h-4" />,
};

export function CharacterPanel() {
  const { character } = useGameStore();

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
            {character.name}
          </h3>
          <div className="flex items-center justify-center gap-2">
            <span className="px-3 py-1 bg-gradient-to-r from-[#c9a227]/20 to-[#c9a227]/10 border border-[#c9a227]/50 rounded-full text-[#c9a227] text-sm font-medium">
              {character.realm}·{character.realmStage}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
