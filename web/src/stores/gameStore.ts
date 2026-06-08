import { create } from 'zustand';
import type { CharacterState, WorldState } from '../types';
import { config } from '../config';
import { getOrCreateUserId, getAuthHeaders } from '../lib/user';

// 时辰定义（与后端 world_time_service.py 保持一致）
const SHICHEN_LIST = [
  { name: '子时', period: '深夜', start: 23, end: 1 },
  { name: '丑时', period: '凌晨', start: 1, end: 3 },
  { name: '寅时', period: '黎明', start: 3, end: 5 },
  { name: '卯时', period: '清晨', start: 5, end: 7 },
  { name: '辰时', period: '早晨', start: 7, end: 9 },
  { name: '巳时', period: '上午', start: 9, end: 11 },
  { name: '午时', period: '正午', start: 11, end: 13 },
  { name: '未时', period: '午后', start: 13, end: 15 },
  { name: '申时', period: '下午', start: 15, end: 17 },
  { name: '酉时', period: '黄昏', start: 17, end: 19 },
  { name: '戌时', period: '傍晚', start: 19, end: 21 },
  { name: '亥时', period: '夜晚', start: 21, end: 23 },
];

function getShichen(hour: number): { name: string; period: string; index: number } {
  if (hour === 23 || hour === 0) {
    return { name: '子时', period: '深夜', index: 0 };
  }
  for (let idx = 0; idx < SHICHEN_LIST.length; idx++) {
    const sc = SHICHEN_LIST[idx];
    if (sc.start <= hour && hour < sc.end) {
      return { name: sc.name, period: sc.period, index: idx };
    }
  }
  return { name: '子时', period: '深夜', index: 0 };
}

function advanceGameTime(state: WorldState, minutes: number): Partial<WorldState> {
  const totalMinutes = state.gameHour * 60 + state.gameMinute + minutes;
  const newHour = Math.floor(totalMinutes / 60) % 24;
  const newMinute = totalMinutes % 60;

  const shichen = getShichen(newHour);
  const updates: Partial<WorldState> = {
    gameHour: newHour,
    gameMinute: newMinute,
    time: shichen.name,
    timePeriod: shichen.period,
    shichenIndex: shichen.index,
  };

  return updates;
}

interface GameState {
  character: CharacterState;
  world: WorldState;
  updateCharacter: (updates: Partial<CharacterState>) => void;
  updateWorld: (updates: Partial<WorldState>) => void;
  characterLayout: string | null;
  worldLayout: string | null;
  isGeneratingCharacterLayout: boolean;
  isGeneratingWorldLayout: boolean;
  _layoutGenerationQueue: { character: boolean; world: boolean };
  setCharacterLayout: (layout: string | null) => void;
  setWorldLayout: (layout: string | null) => void;
  loadLayout: (panelType: 'character' | 'world') => Promise<void>;
  generateLayout: (panelType: 'character' | 'world') => Promise<void>;
  regenerateLayout: (panelType: 'character' | 'world') => Promise<void>;
  loadUserInfo: () => Promise<void>;
  worldTimeSSE: EventSource | null;
  connectWorldTimeSSE: () => void;
  disconnectWorldTimeSSE: () => void;
  fetchWorldTime: () => Promise<void>;
  // 时间同步内部状态和方法
  _worldTimeTickInterval: number | null;
  _worldTimePollInterval: number | null;
  _lastServerSyncAt: number;
  _syncWorldTime: (data: Partial<WorldState> & { gameMinute?: number }) => void;
  _startLocalWorldTimeTick: () => void;
  _stopLocalWorldTimeTick: () => void;
  _startWorldTimePolling: () => void;
  _stopWorldTimePolling: () => void;
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
  gameDate: '',
  gameHour: 0,
  gameMinute: 0,
  shichenIndex: 0,
};

export const useGameStore = create<GameState>((set, get) => ({
  character: initialCharacter,
  world: initialWorld,
  characterLayout: null,
  worldLayout: null,
  isGeneratingCharacterLayout: false,
  isGeneratingWorldLayout: false,
  _layoutGenerationQueue: { character: false, world: false },
  worldTimeSSE: null,
  _worldTimeTickInterval: null,
  _worldTimePollInterval: null,
  _lastServerSyncAt: 0,

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

    // 防抖：如果正在生成中，标记需要重新生成，等当前生成完成后再触发
    const isGenerating = panelType === 'character'
      ? useGameStore.getState().isGeneratingCharacterLayout
      : useGameStore.getState().isGeneratingWorldLayout;

    if (isGenerating) {
      // 标记需要重新生成
      useGameStore.setState((state) => ({
        _layoutGenerationQueue: {
          ...state._layoutGenerationQueue,
          [panelType]: true,
        },
      }));
      console.log(`[Layout] ${panelType} 正在生成中，标记待重新生成`);
      return;
    }

    // 设置生成状态
    if (panelType === 'character') {
      set({ isGeneratingCharacterLayout: true });
    } else {
      set({ isGeneratingWorldLayout: true });
    }

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
    } finally {
      // 清除生成状态
      if (panelType === 'character') {
        set({ isGeneratingCharacterLayout: false });
      } else {
        set({ isGeneratingWorldLayout: false });
      }

      // 检查是否需要重新生成（防抖后重试）
      const queueState = useGameStore.getState()._layoutGenerationQueue;
      if (queueState[panelType]) {
        // 清除标记并重新生成
        useGameStore.setState((state) => ({
          _layoutGenerationQueue: {
            ...state._layoutGenerationQueue,
            [panelType]: false,
          },
        }));
        console.log(`[Layout] ${panelType} 检测到待重新生成标记，开始重新生成`);
        // 使用 setTimeout 避免递归过深
        setTimeout(() => {
          useGameStore.getState().generateLayout(panelType);
        }, 100);
      }
    }
  },

  _syncWorldTime: (data) => {
    const now = Date.now();
    set((state) => {
      const updates: Partial<WorldState> = {};
      if (typeof data.gameDate === 'string') updates.gameDate = data.gameDate;
      if (typeof data.gameHour === 'number') updates.gameHour = data.gameHour;
      if (typeof data.gameMinute === 'number') updates.gameMinute = data.gameMinute;
      if (typeof data.time === 'string') updates.time = data.time;
      if (typeof data.timePeriod === 'string') updates.timePeriod = data.timePeriod;
      if (typeof data.shichenIndex === 'number') updates.shichenIndex = data.shichenIndex;

      // 如果服务端只给了 gameHour 没给 gameMinute，默认补 0
      if (typeof data.gameHour === 'number' && typeof data.gameMinute !== 'number') {
        updates.gameMinute = 0;
      }

      // 如果给了 gameHour 和 gameMinute 但没给 time，自动计算
      if ((typeof updates.gameHour === 'number' || typeof state.world.gameHour === 'number')
        && (typeof updates.gameMinute === 'number' || typeof state.world.gameMinute === 'number')) {
        const hour = updates.gameHour ?? state.world.gameHour;
        const minute = updates.gameMinute ?? state.world.gameMinute;
        const shichen = getShichen(hour);
        updates.time = shichen.name;
        updates.timePeriod = shichen.period;
        updates.shichenIndex = shichen.index;
        updates.gameHour = hour;
        updates.gameMinute = minute;
      }

      return {
        world: { ...state.world, ...updates },
        _lastServerSyncAt: now,
      };
    });
  },

  _startLocalWorldTimeTick: () => {
    const { _worldTimeTickInterval } = get();
    if (_worldTimeTickInterval) return;

    // 每 6 秒推进 1 游戏分钟（与后端 TICK_INTERVAL = 6 保持一致）
    const interval = window.setInterval(() => {
      set((state) => {
        const updates = advanceGameTime(state.world, 1);
        return { world: { ...state.world, ...updates } };
      });
    }, 6000);

    set({ _worldTimeTickInterval: interval });
    console.log('[WorldTime] 本地时间推进已启动');
  },

  _stopLocalWorldTimeTick: () => {
    const { _worldTimeTickInterval } = get();
    if (_worldTimeTickInterval) {
      clearInterval(_worldTimeTickInterval);
      set({ _worldTimeTickInterval: null });
      console.log('[WorldTime] 本地时间推进已停止');
    }
  },

  _startWorldTimePolling: () => {
    const { _worldTimePollInterval } = get();
    if (_worldTimePollInterval) return;

    // 每 30 秒轮询一次服务端时间作为校准兜底
    const interval = window.setInterval(() => {
      const { fetchWorldTime } = get();
      fetchWorldTime();
    }, 30000);

    set({ _worldTimePollInterval: interval });
    console.log('[WorldTime] 时间轮询已启动');
  },

  _stopWorldTimePolling: () => {
    const { _worldTimePollInterval } = get();
    if (_worldTimePollInterval) {
      clearInterval(_worldTimePollInterval);
      set({ _worldTimePollInterval: null });
      console.log('[WorldTime] 时间轮询已停止');
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

      // 加载世界时间并启动时间同步机制
      const state = get();
      await state.fetchWorldTime();
      state.connectWorldTimeSSE();
      state._startLocalWorldTimeTick();
      state._startWorldTimePolling();

      // 监听页面可见性变化，切回前台时立即同步时间
      const handleVisibilityChange = () => {
        if (document.visibilityState === 'visible') {
          const { fetchWorldTime } = get();
          fetchWorldTime();
        }
      };
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      document.addEventListener('visibilitychange', handleVisibilityChange);

      // 加载布局
      const { loadLayout } = useGameStore.getState();
      loadLayout('character');
      loadLayout('world');

      // 延迟检查布局是否生成成功，如果未成功则重试
      setTimeout(() => {
        const st = useGameStore.getState();
        if (!st.characterLayout) {
          console.log('[Layout] 角色布局未生成，尝试重新生成');
          st.generateLayout('character');
        }
        if (!st.worldLayout) {
          console.log('[Layout] 世界布局未生成，尝试重新生成');
          st.generateLayout('world');
        }
      }, 3000);
    } catch (error) {
      console.error('加载用户信息失败:', error);
    }
  },

  fetchWorldTime: async () => {
    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/world-time`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      const { _syncWorldTime } = get();
      _syncWorldTime({
        gameDate: data.game_date,
        gameHour: data.game_hour,
        gameMinute: data.game_minute,
        time: data.shichen_name,
        timePeriod: data.shichen_period,
        shichenIndex: data.shichen_index,
      });
    } catch (error) {
      console.error('获取世界时间失败:', error);
    }
  },

  connectWorldTimeSSE: () => {
    // 先断开已有连接
    const { disconnectWorldTimeSSE } = useGameStore.getState();
    disconnectWorldTimeSSE();

    try {
      const eventSource = new EventSource(`${config.API_BASE_URL}/gm/world-time/sse`);

      eventSource.addEventListener('current_time', (event) => {
        try {
          const data = JSON.parse(event.data);
          const { _syncWorldTime } = get();
          _syncWorldTime({
            gameDate: data.game_date,
            gameHour: data.game_hour,
            gameMinute: data.game_minute,
            time: data.shichen_name,
            timePeriod: data.shichen_period,
            shichenIndex: data.shichen_index,
          });
        } catch (e) {
          console.error('解析世界时间SSE数据失败:', e);
        }
      });

      eventSource.addEventListener('shichen_change', (event) => {
        try {
          const data = JSON.parse(event.data);
          const { _syncWorldTime } = get();
          _syncWorldTime({
            gameDate: data.game_date,
            gameHour: data.game_hour,
            gameMinute: data.game_minute,
            time: data.shichen_name,
            timePeriod: data.shichen_period,
            shichenIndex: data.shichen_index,
          });
          console.log(`[WorldTime] 时辰变化: ${data.game_date} ${data.shichen_name}·${data.shichen_period}`);
        } catch (e) {
          console.error('解析时辰变化SSE数据失败:', e);
        }
      });

      eventSource.addEventListener('heartbeat', () => {
        // 心跳事件，仅用于保持连接活跃，无需处理
      });

      eventSource.onerror = () => {
        console.error('世界时间SSE连接错误，5秒后重连');
        eventSource.close();
        set({ worldTimeSSE: null });
        setTimeout(() => {
          useGameStore.getState().connectWorldTimeSSE();
        }, 5000);
      };

      set({ worldTimeSSE: eventSource });
      console.log('[WorldTime] SSE 连接已建立');
    } catch (error) {
      console.error('建立世界时间SSE连接失败:', error);
    }
  },

  disconnectWorldTimeSSE: () => {
    const { worldTimeSSE } = useGameStore.getState();
    if (worldTimeSSE) {
      worldTimeSSE.close();
      set({ worldTimeSSE: null });
      console.log('[WorldTime] SSE 连接已断开');
    }
  },

  regenerateLayout: async (panelType) => {
    // 清除现有布局，强制重新生成
    if (panelType === 'character') {
      set({ characterLayout: null });
    } else {
      set({ worldLayout: null });
    }
    const { generateLayout } = useGameStore.getState();
    await generateLayout(panelType);
  },
}));
