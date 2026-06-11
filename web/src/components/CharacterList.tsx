import { useState, useRef, useEffect } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useChatStore } from '../stores/chatStore';
import { MessageCircle, Sword, Users } from 'lucide-react';
import type { NearbyCharacter } from '../types';

const TYPE_CONFIG: Record<string, { label: string; emoji: string; tagColor: string }> = {
  npc: { label: 'NPC', emoji: '👤', tagColor: 'bg-[#5ab8b8]/20 text-[#5ab8b8]' },
  player: { label: '玩家', emoji: '🧑', tagColor: 'bg-[#c9a227]/20 text-[#c9a227]' },
  monster: { label: '怪物', emoji: '👹', tagColor: 'bg-[#E74C3C]/20 text-[#E74C3C]' },
};

function CharacterItem({ character }: { character: NearbyCharacter }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const itemRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const tooltipTimeoutRef = useRef<number>(0);

  const config = TYPE_CONFIG[character.type] || TYPE_CONFIG.npc;

  // 点击外部关闭菜单
  useEffect(() => {
    if (!showMenu) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node) &&
          itemRef.current && !itemRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu]);

  const handleMouseEnter = () => {
    clearTimeout(tooltipTimeoutRef.current);
    setShowTooltip(true);
  };

  const handleMouseLeave = () => {
    tooltipTimeoutRef.current = window.setTimeout(() => setShowTooltip(false), 200);
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowMenu(!showMenu);
    setShowTooltip(false);
  };

  const handleAction = (action: 'dialog' | 'attack') => {
    const { insertTextAtCursor } = useChatStore.getState();
    if (action === 'dialog') {
      insertTextAtCursor(`与${character.name}对话`);
    } else {
      insertTextAtCursor(`攻击${character.name}`);
    }
    setShowMenu(false);
  };

  return (
    <div
      ref={itemRef}
      className="relative p-2.5 bg-[#1a2f2f]/50 hover:bg-[#2d5a5a]/30 rounded-lg border border-[#2d5a5a]/30 hover:border-[#3d7a7a]/50 cursor-pointer transition-all duration-200"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      <div className="flex items-center gap-2">
        <span className="text-base flex-shrink-0">{character.avatar || config.emoji}</span>
        <span className="text-[#e8e4dc] text-sm font-medium flex-1 truncate" style={{ fontFamily: 'Noto Serif SC, serif' }}>
          {character.name}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 ${config.tagColor}`}>
          {config.label}
        </span>
      </div>

      {/* 悬停信息卡 */}
      {showTooltip && !showMenu && (character.desc || character.currentAction) && (
        <div
          className="absolute left-0 right-0 z-20 mt-1 p-3 bg-[#0d1f1f]/95 border border-[#c9a227]/30 rounded-lg shadow-lg shadow-black/30 backdrop-blur-sm"
          onMouseEnter={() => clearTimeout(tooltipTimeoutRef.current)}
          onMouseLeave={handleMouseLeave}
        >
          {character.desc && (
            <p className="text-[#e8e4dc] text-xs leading-relaxed mb-1.5" style={{ fontFamily: 'Noto Serif SC, serif' }}>
              {character.desc}
            </p>
          )}
          {character.currentAction && (
            <div className="flex items-start gap-1.5">
              <span className="text-[#c9a227] text-[10px] mt-0.5 flex-shrink-0">●</span>
              <p className="text-[#7ababa] text-xs leading-relaxed" style={{ fontFamily: 'Noto Serif SC, serif' }}>
                {character.currentAction}
              </p>
            </div>
          )}
        </div>
      )}

      {/* 点击上下文菜单 */}
      {showMenu && (
        <div
          ref={menuRef}
          className="absolute left-0 right-0 z-30 mt-1 bg-[#1a2f2f] border border-[#2d5a5a]/50 rounded-lg shadow-lg shadow-black/40 overflow-hidden"
        >
          <button
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[#e8e4dc] hover:bg-[#2d5a5a]/30 transition-colors duration-150"
            style={{ fontFamily: 'Noto Serif SC, serif' }}
            onClick={(e) => { e.stopPropagation(); handleAction('dialog'); }}
          >
            <MessageCircle className="w-3.5 h-3.5 text-[#5ab8b8]" />
            <span>对话</span>
          </button>
          <button
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[#e8e4dc] hover:bg-[#2d5a5a]/30 transition-colors duration-150"
            style={{ fontFamily: 'Noto Serif SC, serif' }}
            onClick={(e) => { e.stopPropagation(); handleAction('attack'); }}
          >
            <Sword className="w-3.5 h-3.5 text-[#E74C3C]" />
            <span>攻击</span>
          </button>
        </div>
      )}
    </div>
  );
}

export function CharacterList() {
  const { nearbyCharacters, fetchNearbyCharacters } = useGameStore();

  // 首次挂载时加载数据
  useEffect(() => {
    fetchNearbyCharacters();
  }, [fetchNearbyCharacters]);

  if (nearbyCharacters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center">
        <Users className="w-10 h-10 text-[#2d5a5a] mb-3" />
        <p className="text-[#5a7a7a] text-sm" style={{ fontFamily: 'Noto Serif SC, serif' }}>
          暂无附近人物
        </p>
        <p className="text-[#3d5a5a] text-xs mt-1" style={{ fontFamily: 'Noto Serif SC, serif' }}>
          探索世界后，周围的角色将出现在此处
        </p>
      </div>
    );
  }

  return (
    <div className="p-3 space-y-2">
      <div className="flex items-center gap-2 mb-2 px-1">
        <span className="text-[#c9a227] text-xs font-medium">附近人物</span>
        <span className="text-[#5a7a7a] text-[10px]">{nearbyCharacters.length}</span>
      </div>
      {nearbyCharacters.map((character) => (
        <CharacterItem key={character.id} character={character} />
      ))}
    </div>
  );
}
