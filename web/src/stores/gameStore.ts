import { create } from 'zustand';
import type { CharacterState, WorldState } from '../types';

interface GameState {
  character: CharacterState;
  world: WorldState;
  updateCharacter: (updates: Partial<CharacterState>) => void;
  updateWorld: (updates: Partial<WorldState>) => void;
}

const initialCharacter: CharacterState = {
  name: '青云子',
  realm: '炼气期',
  realmStage: '中期',
  spiritRoot: '先天水灵根',
  level: 12,
  health: 850,
  maxHealth: 1000,
  mana: 420,
  maxMana: 500,
  spirit: 180,
  maxSpirit: 200,
  equipment: [
    { id: '1', name: '青锋剑', type: 'weapon', icon: 'sword' },
    { id: '2', name: '云纹袍', type: 'armor', icon: 'shield' },
    { id: '3', name: '聚灵戒', type: 'accessory', icon: 'circle' },
  ],
};

const initialWorld: WorldState = {
  time: '子时',
  timePeriod: '深夜',
  weather: '晴朗',
  weatherDesc: '微风',
  spiritTide: true,
  spiritTideIntensity: 3,
  location: '青云古域·云溪村',
  events: [
    {
      id: '1',
      title: '灵潮涌动',
      description: '每月十五，灵气浓度短暂提升',
      timestamp: Date.now(),
      type: 'important',
    },
    {
      id: '2',
      title: '秘境现世',
      description: '荒古野域发现新的上古秘境入口',
      timestamp: Date.now() - 3600000,
      type: 'normal',
    },
    {
      id: '3',
      title: '宗门招募',
      description: '青云宗开始招收新弟子',
      timestamp: Date.now() - 7200000,
      type: 'normal',
    },
  ],
};

export const useGameStore = create<GameState>((set) => ({
  character: initialCharacter,
  world: initialWorld,
  updateCharacter: (updates) =>
    set((state) => ({
      character: { ...state.character, ...updates },
    })),
  updateWorld: (updates) =>
    set((state) => ({
      world: { ...state.world, ...updates },
    })),
}));
