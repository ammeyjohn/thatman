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
    <div className="w-[280px] bg-gradient-to-b from-[#0d1f1f] to-[#0a1515] border-r border-[#2d5a5a]/30 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-[#2d5a5a]/30">
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

        {/* Spirit Root */}
        <div className="mb-6 p-3 bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#a0c0c0]">灵根</span>
            <span className="text-sm text-[#3d9a9a] font-medium">{character.spiritRoot}</span>
          </div>
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-[#a0c0c0]">等级</span>
            <span className="text-sm text-[#e8e4dc] font-medium">Lv.{character.level}</span>
          </div>
        </div>

        {/* Status Bars */}
        <div className="mb-6">
          <StatusBar
            label="生命"
            current={character.health}
            max={character.maxHealth}
            color="#c94e4e"
            icon="❤️"
          />
          <StatusBar
            label="灵力"
            current={character.mana}
            max={character.maxMana}
            color="#4e8ac9"
            icon="✨"
          />
          <StatusBar
            label="神识"
            current={character.spirit}
            max={character.maxSpirit}
            color="#9a4ec9"
            icon="👁"
          />
        </div>

        {/* Equipment */}
        <div>
          <h4 className="text-[#a0c0c0] text-sm font-medium mb-3 flex items-center gap-2">
            <span>⚔️</span>
            <span>装备</span>
          </h4>
          <div className="grid grid-cols-3 gap-2">
            {character.equipment.map((item) => (
              <div
                key={item.id}
                className="aspect-square bg-[#1a2f2f]/50 rounded-lg border border-[#2d5a5a]/30 flex flex-col items-center justify-center gap-1 hover:border-[#c9a227]/50 transition-colors cursor-pointer group"
                title={item.name}
              >
                <div className="text-[#3d7a7a] group-hover:text-[#c9a227] transition-colors">
                  {equipmentIcons[item.icon]}
                </div>
                <span className="text-[10px] text-[#a0c0c0] truncate w-full text-center px-1">
                  {item.name}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
