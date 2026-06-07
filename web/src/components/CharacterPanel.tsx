import React, { useState, useRef, useEffect } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useAuthStore } from '../stores/authStore';
import { useNavigate } from 'react-router-dom';
import { StatusBar } from './StatusBar';
import { Sword, Shield, Circle, Sparkles, MapPin, Activity, TrendingUp, Clock, Shirt, Package, MoreHorizontal, LogOut, Settings, User } from 'lucide-react';

const equipmentIcons: Record<string, React.ReactNode> = {
  sword: <Sword className="w-4 h-4" />,
  shield: <Shield className="w-4 h-4" />,
  circle: <Circle className="w-4 h-4" />,
};

export function CharacterPanel() {
  const { character, characterLayout } = useGameStore();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // 注入实时数据到 window.__LAYOUT_DATA__，供 HTML 布局中的 JS 读取
  React.useEffect(() => {
    if (characterLayout) {
      (window as any).__LAYOUT_DATA__ = character;
    }
  }, [character, characterLayout]);

  // 点击外部关闭菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [menuOpen]);

  const handleLogout = () => {
    useAuthStore.getState().logout();
    navigate('/login');
  };

  return (
    <div className="w-[280px] bg-[#0d1f1f] border-r border-[#2d5a5a]/30 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-[#2d5a5a]/30 bg-[#0d1f1f] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-[#c9a227]" />
          <h2 className="text-[#e8e4dc] font-bold text-lg" style={{ fontFamily: 'Noto Serif SC, serif' }}>
            角色状态
          </h2>
        </div>
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex items-center justify-center w-8 h-8 rounded-md bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#c9a227] hover:border-[#c9a227]/50 transition-colors duration-200 cursor-pointer"
            title="更多选项"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-36 bg-[#1a2f2f] border border-[#2d5a5a]/50 rounded-md shadow-lg shadow-black/30 py-1 z-50">
              <button
                className="flex items-center gap-2 w-full px-3 py-2 text-xs text-[#a0c0c0] hover:bg-[#2d5a5a]/30 hover:text-[#e8e4dc] transition-colors duration-150 cursor-pointer"
              >
                <User className="w-3.5 h-3.5" />
                角色信息
              </button>
              <button
                className="flex items-center gap-2 w-full px-3 py-2 text-xs text-[#a0c0c0] hover:bg-[#2d5a5a]/30 hover:text-[#e8e4dc] transition-colors duration-150 cursor-pointer"
              >
                <Settings className="w-3.5 h-3.5" />
                设置
              </button>
              <div className="border-t border-[#2d5a5a]/30 my-1" />
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 w-full px-3 py-2 text-xs text-[#E74C3C] hover:bg-[#E74C3C]/10 transition-colors duration-150 cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" />
                退出
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {characterLayout ? (
          // 动态 HTML 布局渲染
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
            {/* 注入实时数据并渲染 HTML 布局 */}
            <div dangerouslySetInnerHTML={{ __html: characterLayout }} />
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
