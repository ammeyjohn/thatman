import { create } from 'zustand';
import type { CharacterState, WorldState } from '../types';
import { config } from '../config';
import { getOrCreateUserId, getAuthHeaders } from '../lib/user';

interface GameState {
  character: CharacterState;
  world: WorldState;
  updateCharacter: (updates: Partial<CharacterState>) => void;
  updateWorld: (updates: Partial<WorldState>) => void;
  characterLayout: string | null;
  worldLayout: string | null;
  setCharacterLayout: (layout: string | null) => void;
  setWorldLayout: (layout: string | null) => void;
  loadLayout: (panelType: 'character' | 'world') => Promise<void>;
  generateLayout: (panelType: 'character' | 'world') => Promise<void>;
  loadUserInfo: () => Promise<void>;
}

const initialCharacter: CharacterState = {
  name: '',
  realm: '炼气期',
  realmStage: '中期',
  spiritRoot: '先天水灵根',
  level: 0,
  health: 850,
  maxHealth: 1000,
  mana: 420,
  maxMana: 500,
  spirit: 180,
  maxSpirit: 200,
  equipment: [],
  currentLocation: '',
  currentStatus: '',
  birthDate: '',
  lifespan: '',
  clothing: '',
  inventory: [],
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
  characterLayout: null,
  worldLayout: null,
  updateCharacter: (updates) =>
    set((state) => ({
      character: { ...state.character, ...updates },
    })),
  updateWorld: (updates) =>
    set((state) => ({
      world: { ...state.world, ...updates },
    })),
  setCharacterLayout: (layout) => set({ characterLayout: layout }),
  setWorldLayout: (layout) => set({ worldLayout: layout }),

  loadLayout: async (panelType) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/layout?uid=${encodeURIComponent(uid)}&panel_type=${panelType}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取布局失败:', response.status);
        return;
      }

      const data = await response.json();
      if (data.layout && typeof data.layout === 'string' && data.layout.trim()) {
        if (panelType === 'character') {
          set({ characterLayout: data.layout });
        } else {
          set({ worldLayout: data.layout });
        }
        console.log(`[Layout] ${panelType} 布局加载成功`);
      } else {
        // 无已保存布局，自动生成
        console.log(`[Layout] ${panelType} 无已保存布局，开始生成`);
        const { generateLayout } = useGameStore.getState();
        generateLayout(panelType);
      }
    } catch (error) {
      console.error('加载布局失败:', error);
    }
  },

  generateLayout: async (panelType) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const gameState = useGameStore.getState();
      const currentData = panelType === 'character' ? gameState.character : gameState.world;

      const response = await fetch(`${config.API_BASE_URL}/gm/generate-layout`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          uid,
          panel_type: panelType,
          current_data: currentData,
        }),
      });

      if (!response.ok) {
        console.error('生成布局失败:', response.status);
        return;
      }

      const data = await response.json();
      if (data.layout) {
        if (panelType === 'character') {
          set({ characterLayout: data.layout });
        } else {
          set({ worldLayout: data.layout });
        }
        console.log(`[Layout] ${panelType} 布局生成成功`);
      }
    } catch (error) {
      console.error('生成布局失败:', error);
    }
  },

  loadUserInfo: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      // 先初始化用户（如果不存在则创建）
      await fetch(`${config.API_BASE_URL}/user/init`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid }),
      });

      // 获取用户信息
      const response = await fetch(`${config.API_BASE_URL}/user/info?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取用户信息失败:', response.status);
        return;
      }

      const data = await response.json();
      if (!data.exists || !data.info) return;

      const info = data.info;
      const charUpdates: Partial<CharacterState> = {};

      if (typeof info.name === 'string' && info.name) charUpdates.name = info.name;
      if (typeof info.current_location === 'string' && info.current_location) {
        charUpdates.currentLocation = info.current_location;
      }
      if (typeof info.current_status === 'string' && info.current_status) {
        charUpdates.currentStatus = info.current_status;
      }
      if (typeof info.birth_date === 'string' && info.birth_date) {
        charUpdates.birthDate = info.birth_date;
      }
      if (typeof info.lifespan === 'string' && info.lifespan) {
        charUpdates.lifespan = info.lifespan;
      }
      if (typeof info.clothing === 'string' && info.clothing) {
        charUpdates.clothing = info.clothing;
      }
      if (Array.isArray(info.inventory)) charUpdates.inventory = info.inventory;
      if (typeof info.realm === 'string') charUpdates.realm = info.realm;
      if (typeof info.realm_stage === 'string') charUpdates.realmStage = info.realm_stage;
      if (typeof info.level === 'number') charUpdates.level = info.level;
      if (typeof info.health === 'number') charUpdates.health = info.health;
      if (typeof info.max_health === 'number') charUpdates.maxHealth = info.max_health;
      if (typeof info.mana === 'number') charUpdates.mana = info.mana;
      if (typeof info.max_mana === 'number') charUpdates.maxMana = info.max_mana;
      if (typeof info.spirit === 'number') charUpdates.spirit = info.spirit;
      if (typeof info.max_spirit === 'number') charUpdates.maxSpirit = info.max_spirit;
      if (Array.isArray(info.equipment)) charUpdates.equipment = info.equipment;

      if (Object.keys(charUpdates).length > 0) {
        set((state) => ({
          character: { ...state.character, ...charUpdates },
        }));
      }

      // 同步更新 world.location
      if (charUpdates.currentLocation) {
        set((state) => ({
          world: { ...state.world, location: charUpdates.currentLocation! },
        }));
      }

      console.log('[UserInfo] 用户信息加载成功');

      // 加载布局
      const { loadLayout } = useGameStore.getState();
      loadLayout('character');
      loadLayout('world');
    } catch (error) {
      console.error('加载用户信息失败:', error);
    }
  },
}));
