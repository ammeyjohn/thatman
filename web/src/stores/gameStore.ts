import { create } from 'zustand';
import type { CharacterState, WorldState, ActionState, TimeAdvanceInfo, KeyEvent, CharacterHistory, NearbyCharacter, KarmaRecord, KarmaBond, OnlinePlayer, SpiritStones, Stall } from '../types';
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
  eventsSSE: EventSource | null;
  connectEventsSSE: () => void;
  disconnectEventsSSE: () => void;
  fetchWorldTime: () => Promise<void>;
  fetchWeather: () => Promise<void>;
  fetchInventory: () => Promise<void>;
  deleteInventoryItem: (itemId: string) => Promise<void>;
  fetchEquipment: () => Promise<void>;
  fetchBusyState: () => Promise<void>;
  interruptAction: () => Promise<void>;
  handleTimeAdvance: (timeAdvance: TimeAdvanceInfo) => void;
  handleBusyState: (actionState: ActionState) => void;
  _syncWorldTime: (data: Partial<WorldState> & { gameMinute?: number }) => void;
  _busyStateCheckInterval: number | null;
  _startBusyStateCheck: () => void;
  _stopBusyStateCheck: () => void;
  keyEvents: KeyEvent[];
  fetchKeyEvents: () => Promise<void>;
  deleteKeyEvent: (eventId: string) => Promise<void>;
  historyList: CharacterHistory[];
  historyDates: string[];
  fetchHistory: (gameDate?: string) => Promise<void>;
  fetchHistoryDates: () => Promise<void>;
  nearbyCharacters: NearbyCharacter[];
  _lastFetchNearbyTime: number;
  fetchNearbyCharacters: () => Promise<void>;
  karmaRecords: KarmaRecord[];
  karmaBonds: KarmaBond[];
  fetchKarmaStatus: () => Promise<void>;
  fetchKarmaBonds: () => Promise<void>;
  onlinePlayers: OnlinePlayer[];
  onlineCount: number;
  _heartbeatInterval: number | null;
  _startHeartbeat: () => void;
  _stopHeartbeat: () => void;
  sendHeartbeat: () => Promise<void>;
  fetchOnlinePlayers: () => Promise<void>;
  // 灵石与摊位
  myStall: Stall | null;
  nearbyStalls: Stall[];
  fetchSpiritStones: () => Promise<void>;
  fetchMyStall: () => Promise<void>;
  fetchNearbyStalls: () => Promise<void>;
  createStall: (stallName: string, items: Array<{ item_id: string; name: string; type?: string; description?: string; quantity: number; price?: number }>) => Promise<void>;
  closeMyStall: () => Promise<void>;
  buyFromStall: (stallId: string, itemId: string, quantity: number) => Promise<void>;
  sellToStall: (stallId: string, itemId: string, quantity: number, price?: number) => Promise<void>;
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
  busyState: null,
  actionState: null,
  lastTimeCost: 0,
  karma: 0,
  karmaLevel: 3,
  karmaTitle: '因果清净',
  spiritStones: { low: 100, medium: 0, high: 0, top: 0 },
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
  eventsSSE: null,
  keyEvents: [],
  historyList: [],
  historyDates: [],
  nearbyCharacters: [],
  _lastFetchNearbyTime: 0,
  karmaRecords: [],
  karmaBonds: [],
  onlinePlayers: [],
  onlineCount: 0,
  _heartbeatInterval: null,
  myStall: null,
  nearbyStalls: [],

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

  connectEventsSSE: () => {
    const { disconnectEventsSSE } = get();
    disconnectEventsSSE(); // 保证只有一个连接

    try {
      const uid = getOrCreateUserId();
      const sseUrl = uid
        ? `${config.API_BASE_URL}/gm/events/sse?uid=${encodeURIComponent(uid)}`
        : `${config.API_BASE_URL}/gm/events/sse`;

      const eventSource = new EventSource(sseUrl);

      // 处理 current_state：初始化全量状态
      eventSource.addEventListener('current_state', (event) => {
        try {
          const data = JSON.parse(event.data);
          const { _syncWorldTime } = get();
          if (data.time) {
            _syncWorldTime({
              gameDate: data.time.game_date,
              gameHour: data.time.game_hour,
              gameMinute: data.time.game_minute,
              time: data.time.shichen_name,
              timePeriod: data.time.shichen_period,
              shichenIndex: data.time.shichen_index,
            });
          }
          if (data.weather) {
            const updates: Partial<WorldState> = {};
            if (typeof data.weather.weather === 'string') updates.weather = data.weather.weather;
            if (typeof data.weather.weather_desc === 'string') updates.weatherDesc = data.weather.weather_desc;
            if (typeof data.weather.spirit_tide === 'boolean') updates.spiritTide = data.weather.spirit_tide;
            if (typeof data.weather.spirit_tide_intensity === 'number') updates.spiritTideIntensity = data.weather.spirit_tide_intensity;
            if (Object.keys(updates).length > 0) {
              set((state) => ({ world: { ...state.world, ...updates } }));
            }
          }

          // 处理附近在线玩家
          if (Array.isArray(data.nearby_players)) {
            const onlinePlayers: OnlinePlayer[] = data.nearby_players.map((p: Record<string, unknown>) => ({
              uid: (p.uid as string) || '',
              characterName: (p.character_name as string) || '',
              location: (p.location as string) || '',
              realm: (p.realm as string) || '',
              realmStage: (p.realm_stage as string) || '',
              status: (p.status as string) || '',
              lastHeartbeat: (p.last_heartbeat as number) || 0,
              onlineAt: (p.online_at as number) || 0,
            }));
            set({ onlinePlayers });
          }

          // 处理在线人数
          if (typeof data.online_count === 'number') {
            set({ onlineCount: data.online_count });
          }

          console.log('[Events] 全量状态同步成功');
        } catch (e) {
          console.error('解析 current_state SSE 数据失败:', e);
        }
      });

      // 处理 time_change：同步世界时间
      eventSource.addEventListener('time_change', (event) => {
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
          console.log(`[Events] 时辰变化: ${data.game_date} ${data.shichen_name}·${data.shichen_period}`);
        } catch (e) {
          console.error('解析 time_change SSE 数据失败:', e);
        }
      });

      // 处理 weather_change：同步天气
      eventSource.addEventListener('weather_change', (event) => {
        try {
          const data = JSON.parse(event.data);
          const updates: Partial<WorldState> = {};
          if (typeof data.weather === 'string') updates.weather = data.weather;
          if (typeof data.weather_desc === 'string') updates.weatherDesc = data.weather_desc;
          if (typeof data.spirit_tide === 'boolean') updates.spiritTide = data.spirit_tide;
          if (typeof data.spirit_tide_intensity === 'number') updates.spiritTideIntensity = data.spirit_tide_intensity;
          if (Object.keys(updates).length > 0) {
            set((state) => ({ world: { ...state.world, ...updates } }));
            console.log(`[Events] 天气变化: ${data.weather}·${data.weather_desc}`);
          }
        } catch (e) {
          console.error('解析 weather_change SSE 数据失败:', e);
        }
      });

      // 处理 layout_change：触发布局生成
      eventSource.addEventListener('layout_change', (event) => {
        try {
          const data = JSON.parse(event.data);
          const { generateLayout } = useGameStore.getState();
          if (data.panel_type === 'character' || data.panel_type === 'both') {
            generateLayout('character');
          }
          if (data.panel_type === 'world' || data.panel_type === 'both') {
            generateLayout('world');
          }
          console.log(`[Events] 布局变化: panel_type=${data.panel_type}`);
        } catch (e) {
          console.error('解析 layout_change SSE 数据失败:', e);
        }
      });

      // 处理 world_event：添加到事件列表，并推送到聊天窗口
      eventSource.addEventListener('world_event', (event) => {
        try {
          const data = JSON.parse(event.data);
          set((state) => ({
            world: {
              ...state.world,
              events: [data, ...state.world.events].slice(0, 50),
            },
          }));

          // 推送到聊天窗口（动态导入避免循环依赖）
          const eventId = data.id || `world_event_${Date.now()}`;
          const title = data.title || '';
          const description = data.description || '';
          if (title || description) {
            import('./chatStore').then(({ useChatStore }) => {
              useChatStore.getState().addEventMessage(String(eventId), String(title), String(description));
            }).catch((err) => {
              console.error('[Events] 推送 world_event 到聊天窗口失败:', err);
            });
          }

          console.log(`[Events] 世界事件: ${data.title}`);
        } catch (e) {
          console.error('解析 world_event SSE 数据失败:', e);
        }
      });

      // 心跳：无操作
      eventSource.addEventListener('heartbeat', () => {
        // 心跳事件，仅用于保持连接活跃，无需处理
      });

      // 处理 player_online：玩家上线
      eventSource.addEventListener('player_online', (event) => {
        try {
          const data = JSON.parse(event.data);
          const newPlayer: OnlinePlayer = {
            uid: data.uid || '',
            characterName: data.character_name || '',
            location: data.location || '',
            realm: data.realm || '',
            realmStage: data.realm_stage || '',
            status: data.status || '',
            lastHeartbeat: 0,
            onlineAt: data.online_at || Date.now() / 1000,
          };
          set((state) => {
            const filtered = state.onlinePlayers.filter(p => p.uid !== newPlayer.uid);
            return {
              onlinePlayers: [...filtered, newPlayer],
              onlineCount: state.onlineCount + (state.onlinePlayers.some(p => p.uid === newPlayer.uid) ? 0 : 1),
            };
          });
          console.log(`[Events] 玩家上线: ${data.character_name}`);
        } catch (e) {
          console.error('解析 player_online SSE 数据失败:', e);
        }
      });

      // 处理 player_offline：玩家下线
      eventSource.addEventListener('player_offline', (event) => {
        try {
          const data = JSON.parse(event.data);
          set((state) => ({
            onlinePlayers: state.onlinePlayers.filter(p => p.uid !== data.uid),
            onlineCount: Math.max(0, state.onlineCount - 1),
          }));
          console.log(`[Events] 玩家下线: ${data.character_name}`);
        } catch (e) {
          console.error('解析 player_offline SSE 数据失败:', e);
        }
      });

      // 处理 player_location_change：玩家位置变化
      eventSource.addEventListener('player_location_change', (event) => {
        try {
          const data = JSON.parse(event.data);
          set((state) => ({
            onlinePlayers: state.onlinePlayers.map(p =>
              p.uid === data.uid ? { ...p, location: data.new_location } : p
            ),
          }));
          console.log(`[Events] 玩家位置变化: ${data.uid} -> ${data.new_location}`);
        } catch (e) {
          console.error('解析 player_location_change SSE 数据失败:', e);
        }
      });

      // 处理 private_message：私聊消息
      eventSource.addEventListener('private_message', (event) => {
        try {
          const data = JSON.parse(event.data);
          // 动态导入 socialStore 处理私聊消息
          import('./socialStore').then(({ useSocialStore }) => {
            useSocialStore.getState().receivePrivateMessage(data);
          }).catch(() => {});
          console.log(`[Events] 收到私聊: ${data.from_name}`);
        } catch (e) {
          console.error('解析 private_message SSE 数据失败:', e);
        }
      });

      // 处理 area_message：区域消息
      eventSource.addEventListener('area_message', (event) => {
        try {
          const data = JSON.parse(event.data);
          import('./socialStore').then(({ useSocialStore }) => {
            useSocialStore.getState().receiveAreaMessage(data);
          }).catch(() => {});
          console.log(`[Events] 区域消息: ${data.from_name}`);
        } catch (e) {
          console.error('解析 area_message SSE 数据失败:', e);
        }
      });

      // 处理 social_request：社交请求（好友/组队/交易/切磋）
      eventSource.addEventListener('social_request', (event) => {
        try {
          const data = JSON.parse(event.data);
          import('./socialStore').then(({ useSocialStore }) => {
            useSocialStore.getState().receiveSocialRequest(data);
          }).catch(() => {});
          console.log(`[Events] 社交请求: ${data.type} from ${data.from_name}`);
        } catch (e) {
          console.error('解析 social_request SSE 数据失败:', e);
        }
      });

      // 错误处理：自动重连
      eventSource.onerror = () => {
        console.error('Events SSE 连接错误，5秒后重连');
        eventSource.close();
        set({ eventsSSE: null });
        setTimeout(() => {
          useGameStore.getState().connectEventsSSE();
        }, 5000);
      };

      set({ eventsSSE: eventSource });
      console.log('[Events] SSE 统一连接已建立');
    } catch (error) {
      console.error('建立 Events SSE 连接失败:', error);
    }
  },

  disconnectEventsSSE: () => {
    const { eventsSSE } = get();
    if (eventsSSE) {
      eventsSSE.close();
      set({ eventsSSE: null });
      // 停止心跳
      useGameStore.getState()._stopHeartbeat();
      console.log('[Events] SSE 统一连接已断开');
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
      if (typeof info.karma === 'number') charUpdates.karma = info.karma;
      if (typeof info.karma_level === 'number') charUpdates.karmaLevel = info.karma_level;
      if (typeof info.karma_title === 'string' && info.karma_title) charUpdates.karmaTitle = info.karma_title;
      if (info.spirit_stones && typeof info.spirit_stones === 'object') {
        charUpdates.spiritStones = {
          low: (info.spirit_stones as Record<string, unknown>).low as number ?? 0,
          medium: (info.spirit_stones as Record<string, unknown>).medium as number ?? 0,
          high: (info.spirit_stones as Record<string, unknown>).high as number ?? 0,
          top: (info.spirit_stones as Record<string, unknown>).top as number ?? 0,
        };
      }

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

      // 先同步一次时间和天气，降低 SSE 建立前的空白期
      const state = get();
      await state.fetchWorldTime();
      await state.fetchWeather();

      // 建立统一 SSE 连接
      state.connectEventsSSE();

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

      // 加载忙碌状态
      useGameStore.getState().fetchBusyState();

      // 加载附近人物
      useGameStore.getState().fetchNearbyCharacters();

      // 启动心跳
      useGameStore.getState()._startHeartbeat();

      // 加载在线玩家
      useGameStore.getState().fetchOnlinePlayers();

      // 加载灵石和摊位数据
      useGameStore.getState().fetchSpiritStones();
      useGameStore.getState().fetchMyStall();
      useGameStore.getState().fetchNearbyStalls();
    } catch (error) {
      console.error('加载用户信息失败:', error);
    }
  },

  fetchInventory: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/inventory?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取储物袋信息失败:', response.status);
        return;
      }

      const data = await response.json();
      if (Array.isArray(data.inventory)) {
        set((state) => ({
          character: { ...state.character, inventory: data.inventory },
        }));
        console.log('[Inventory] 储物袋信息加载成功');
      }
    } catch (error) {
      console.error('获取储物袋信息失败:', error);
    }
  },

  deleteInventoryItem: async (itemId: string) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/gm/inventory/${encodeURIComponent(itemId)}?uid=${encodeURIComponent(uid)}`,
        {
          method: 'DELETE',
          headers: getAuthHeaders(),
        }
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        console.error('删除物品失败:', data?.error?.message || response.status);
        return;
      }

      const data = await response.json();
      if (data.deleted && Array.isArray(data.inventory)) {
        set((state) => ({
          character: { ...state.character, inventory: data.inventory },
        }));
        console.log('[Inventory] 物品已删除:', itemId);
      }
    } catch (error) {
      console.error('删除物品失败:', error);
    }
  },

  fetchEquipment: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/equipment?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取装备信息失败:', response.status);
        return;
      }

      const data = await response.json();
      const charUpdates: Partial<CharacterState> = {};
      if (Array.isArray(data.equipment)) charUpdates.equipment = data.equipment;
      if (typeof data.clothing === 'string') charUpdates.clothing = data.clothing;

      if (Object.keys(charUpdates).length > 0) {
        set((state) => ({
          character: { ...state.character, ...charUpdates },
        }));
        console.log('[Equipment] 装备信息加载成功');
      }
    } catch (error) {
      console.error('获取装备信息失败:', error);
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

  fetchWeather: async () => {
    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/weather`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      const updates: Partial<WorldState> = {};
      if (typeof data.weather === 'string') updates.weather = data.weather;
      if (typeof data.weather_desc === 'string') updates.weatherDesc = data.weather_desc;
      if (typeof data.spirit_tide === 'boolean') updates.spiritTide = data.spirit_tide;
      if (typeof data.spirit_tide_intensity === 'number') updates.spiritTideIntensity = data.spirit_tide_intensity;
      if (Object.keys(updates).length > 0) {
        set((state) => ({ world: { ...state.world, ...updates } }));
        console.log('[Weather] 天气同步成功:', updates);
      }
    } catch (error) {
      console.error('获取天气失败:', error);
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

  fetchBusyState: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/busy-state?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;

      const data = await response.json();

      // 映射后端 snake_case 到前端 camelCase
      const actionState: ActionState | null = data.is_busy && data.action_state
        ? {
            isBusy: true,
            actionId: data.action_state.action_id || '',
            actionName: data.action_state.action_name || '',
            baseTimeCost: data.action_state.base_time_cost || 0,
            finalTimeCost: data.action_state.final_time_cost || 0,
            modifiers: (data.action_state.modifiers || []).map((m: any) => ({
              source: m.source || '',
              factor: m.factor || 0,
              minutes: m.minutes || 0,
            })),
            gameStartTime: {
              date: data.action_state.game_start_time?.date || '',
              hour: data.action_state.game_start_time?.hour || 0,
              minute: data.action_state.game_start_time?.minute || 0,
            },
            cooldownSeconds: data.action_state.cooldown_seconds || 0,
            cooldownRemainingSeconds: data.action_state.cooldown_remaining_seconds || 0,
            cooldownEndAt: data.action_state.cooldown_end_at || 0,
            startedAt: data.action_state.started_at || 0,
            restrictions: {
              forbiddenOperations: data.action_state.restrictions?.forbidden_operations || [],
              allowedOperations: data.action_state.restrictions?.allowed_operations || [],
              allowInterrupt: data.action_state.restrictions?.allow_interrupt ?? true,
              interruptPenalty: data.action_state.restrictions?.interrupt_penalty || 'none',
            },
            status: data.action_state.status || 'active',
          }
        : null;

      set((state) => ({
        character: {
          ...state.character,
          actionState,
          busyState: null, // 逐步废弃旧字段
        },
      }));

      // 如果忙碌，启动冷却检查
      if (data.is_busy && actionState) {
        useGameStore.getState()._startBusyStateCheck();
      }
    } catch (error) {
      console.error('[ActionState] 获取动作状态失败:', error);
    }
  },

  interruptAction: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/interrupt`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid }),
      });
      if (!response.ok) return;

      const data = await response.json();
      if (data.interrupted) {
        set((state) => ({
          character: {
            ...state.character,
            actionState: null,
            busyState: null,
          },
        }));
        useGameStore.getState()._stopBusyStateCheck();
        console.log('[ActionState] 已中断耗时行为:', data.message);
      } else {
        console.log('[ActionState] 中断被拒绝:', data.message);
      }
    } catch (error) {
      console.error('[ActionState] 中断耗时行为失败:', error);
    }
  },

  handleTimeAdvance: (timeAdvance: TimeAdvanceInfo) => {
    const newTime = timeAdvance.new_time;
    set((state) => ({
      character: {
        ...state.character,
        lastTimeCost: timeAdvance.advanced_minutes,
      },
      world: {
        ...state.world,
        gameDate: newTime.game_date,
        gameHour: newTime.game_hour,
        gameMinute: newTime.game_minute,
        time: newTime.shichen_name,
        timePeriod: newTime.shichen_period,
        shichenIndex: newTime.shichen_index,
      },
    }));
    console.log(`[TimeAdvance] 时间推进: +${timeAdvance.advanced_minutes}分钟, 原因=${timeAdvance.reason}`);
  },

  handleBusyState: (actionState: ActionState) => {
    set((state) => ({
      character: {
        ...state.character,
        actionState: actionState,
        busyState: null,
      },
    }));
    // 启动冷却检查
    useGameStore.getState()._startBusyStateCheck();
    console.log(`[ActionState] 进入动作状态: ${actionState.actionName}, 冷却${actionState.cooldownSeconds}秒`);
  },

  _busyStateCheckInterval: null,

  _startBusyStateCheck: () => {
    const { _busyStateCheckInterval } = get();
    if (_busyStateCheckInterval) return;

    // 每2秒检查一次冷却是否结束
    const interval = window.setInterval(() => {
      const { actionState } = get().character;
      if (!actionState) {
        useGameStore.getState()._stopBusyStateCheck();
        return;
      }

      const now = Date.now();
      if (now >= actionState.cooldownEndAt) {
        // 冷却结束，清除动作状态
        set((state) => ({
          character: {
            ...state.character,
            actionState: null,
            busyState: null,
          },
        }));
        useGameStore.getState()._stopBusyStateCheck();
        console.log('[ActionState] 冷却结束，动作状态已清除');
      }
    }, 2000);

    set({ _busyStateCheckInterval: interval });
  },

  _stopBusyStateCheck: () => {
    const { _busyStateCheckInterval } = get();
    if (_busyStateCheckInterval) {
      clearInterval(_busyStateCheckInterval);
      set({ _busyStateCheckInterval: null });
      console.log('[BusyState] 冷却检查已停止');
    }
  },

  fetchKeyEvents: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/key-events?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取关键事件失败:', response.status);
        return;
      }

      const data = await response.json();
      if (Array.isArray(data.events)) {
        const keyEvents: KeyEvent[] = data.events.map((e: Record<string, unknown>, index: number) => ({
          id: (e._id as string) || (e.id as string) || `temp-${index}-${Date.now()}`,
          uid: (e.uid as string) || '',
          title: (e.title as string) || '',
          description: (e.description as string) || '',
          status: (e.status as 'ongoing' | 'completed') || 'ongoing',
          sourceMessageId: (e.source_message_id as string) || undefined,
          createdAt: (e.created_at as string) || '',
          updatedAt: (e.updated_at as string) || '',
        }));
        set({ keyEvents });
        console.log('[KeyEvents] 关键事件加载成功:', keyEvents.length);
      }
    } catch (error) {
      console.error('获取关键事件失败:', error);
    }
  },

  deleteKeyEvent: async (eventId: string) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(
        `${config.API_BASE_URL}/gm/key-events/${encodeURIComponent(eventId)}?uid=${encodeURIComponent(uid)}`,
        {
          method: 'DELETE',
          headers: getAuthHeaders(),
        }
      );
      if (!response.ok) {
        console.error('删除关键事件失败:', response.status);
        return;
      }

      set((state) => ({
        keyEvents: state.keyEvents.filter((e) => e.id !== eventId),
      }));
      console.log('[KeyEvents] 关键事件已删除:', eventId);
    } catch (error) {
      console.error('删除关键事件失败:', error);
    }
  },

  fetchHistory: async (gameDate?: string) => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      let url = `${config.API_BASE_URL}/gm/history?uid=${encodeURIComponent(uid)}`;
      if (gameDate) {
        url += `&game_date=${encodeURIComponent(gameDate)}`;
      }
      const response = await fetch(url, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取历史记录失败:', response.status);
        return;
      }

      const data = await response.json();
      if (Array.isArray(data.history)) {
        const historyList: CharacterHistory[] = data.history.map((h: Record<string, unknown>) => ({
          id: (h._id as string) || (h.id as string) || '',
          uid: (h.uid as string) || '',
          gameDate: (h.game_date as string) || '',
          entries: (Array.isArray(h.entries) ? h.entries : []).map((e: Record<string, unknown>) => ({
            period: (e.period as string) || '',
            summary: (e.summary as string) || '',
            location: (e.location as string) || '',
            realmSnapshot: (e.realm_snapshot as string) || '',
            keyChanges: Array.isArray(e.key_changes) ? e.key_changes as string[] : [],
            sourceMessageId: (e.source_message_id as string) || undefined,
            timestamp: (e.timestamp as number) || 0,
          })),
          dailySummary: (h.daily_summary as string) || '',
          createdAt: (h.created_at as string) || '',
          updatedAt: (h.updated_at as string) || '',
        }));
        set({ historyList });
        console.log('[History] 历史记录加载成功:', historyList.length);
      }
      if (Array.isArray(data.dates)) {
        set({ historyDates: data.dates as string[] });
      }
    } catch (error) {
      console.error('获取历史记录失败:', error);
    }
  },

  fetchHistoryDates: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/history/dates?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取历史日期失败:', response.status);
        return;
      }

      const data = await response.json();
      if (Array.isArray(data.dates)) {
        set({ historyDates: data.dates as string[] });
        console.log('[History] 历史日期加载成功:', data.dates.length);
      }
    } catch (error) {
      console.error('获取历史日期失败:', error);
    }
  },

  fetchNearbyCharacters: async () => {
    // 防抖：30秒内不重复调用
    const now = Date.now();
    const lastFetchTime = useGameStore.getState()._lastFetchNearbyTime;
    if (now - lastFetchTime < 30000) {
      return;
    }

    const uid = getOrCreateUserId();
    if (!uid) return;

    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/nearby-characters?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        console.error('获取附近人物失败:', response.status);
        return;
      }

      const data = await response.json();
      if (Array.isArray(data.characters)) {
        const characters: NearbyCharacter[] = data.characters.map((c: Record<string, unknown>) => ({
          id: (c.id as string) || `char_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
          name: (c.name as string) || '',
          type: (c.type as 'npc' | 'player' | 'monster') || 'npc',
          desc: (c.desc as string) || '',
          currentAction: (c.current_action as string) || (c.currentAction as string) || '',
          avatar: (c.avatar as string) || undefined,
          uid: (c.uid as string) || undefined,
          isOnline: (c.isOnline as boolean) || undefined,
          hasStall: (c.hasStall as boolean) || false,
          stallId: (c.stallId as string) || undefined,
          stallName: (c.stallName as string) || undefined,
        }));
        set({ nearbyCharacters: characters, _lastFetchNearbyTime: Date.now() });
        console.log('[NearbyCharacters] 附近人物加载成功:', characters.length);
      }
    } catch (error) {
      console.error('获取附近人物失败:', error);
    }
  },

  fetchKarmaStatus: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/karma?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      const charUpdates: Partial<CharacterState> = {};
      if (typeof data.karma === 'number') charUpdates.karma = data.karma;
      if (typeof data.karma_level === 'number') charUpdates.karmaLevel = data.karma_level;
      if (typeof data.karma_title === 'string') charUpdates.karmaTitle = data.karma_title;
      if (Object.keys(charUpdates).length > 0) {
        set((state) => ({ character: { ...state.character, ...charUpdates } }));
      }
      if (Array.isArray(data.recent_records)) {
        set({ karmaRecords: data.recent_records });
      }
      if (Array.isArray(data.bonds)) {
        set({ karmaBonds: data.bonds });
      }
      console.log('[Karma] 业力状态加载成功');
    } catch (error) {
      console.error('获取业力状态失败:', error);
    }
  },

  fetchKarmaBonds: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/karma/bonds?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data.bonds)) {
        set({ karmaBonds: data.bonds });
      }
      console.log('[Karma] 因果羁绊加载成功');
    } catch (error) {
      console.error('获取因果羁绊失败:', error);
    }
  },

  // ───────────────────────────────────────────────
  // 在线玩家与心跳
  // ───────────────────────────────────────────────

  sendHeartbeat: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/heartbeat`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid }),
      });
      if (response.ok) {
        const data = await response.json();
        set({ onlineCount: data.online_count ?? 0 });
      }
    } catch (error) {
      console.error('[Heartbeat] 心跳发送失败:', error);
    }
  },

  _startHeartbeat: () => {
    const { _heartbeatInterval } = get();
    if (_heartbeatInterval) return;

    // 立即发送一次
    useGameStore.getState().sendHeartbeat();

    // 每30秒发送心跳
    const interval = window.setInterval(() => {
      useGameStore.getState().sendHeartbeat();
    }, 30000);

    set({ _heartbeatInterval: interval });
    console.log('[Heartbeat] 心跳已启动');
  },

  _stopHeartbeat: () => {
    const { _heartbeatInterval } = get();
    if (_heartbeatInterval) {
      clearInterval(_heartbeatInterval);
      set({ _heartbeatInterval: null });
      console.log('[Heartbeat] 心跳已停止');
    }
  },

  fetchOnlinePlayers: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/gm/online-players?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data.players)) {
        const onlinePlayers: OnlinePlayer[] = data.players.map((p: Record<string, unknown>) => ({
          uid: (p.uid as string) || '',
          characterName: (p.character_name as string) || '',
          location: (p.location as string) || '',
          realm: (p.realm as string) || '',
          realmStage: (p.realm_stage as string) || '',
          status: (p.status as string) || '',
          lastHeartbeat: (p.last_heartbeat as number) || 0,
          onlineAt: (p.online_at as number) || 0,
        }));
        set({ onlinePlayers, onlineCount: data.online_count ?? onlinePlayers.length });
        console.log('[OnlinePlayers] 在线玩家加载成功:', onlinePlayers.length);
      }
    } catch (error) {
      console.error('获取在线玩家失败:', error);
    }
  },

  // ───────────────────────────────────────────────
  // 灵石与摊位
  // ───────────────────────────────────────────────

  fetchSpiritStones: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/market/spirit-stones?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      if (data.spirit_stones) {
        set((state) => ({
          character: {
            ...state.character,
            spiritStones: {
              low: data.spirit_stones.low ?? 0,
              medium: data.spirit_stones.medium ?? 0,
              high: data.spirit_stones.high ?? 0,
              top: data.spirit_stones.top ?? 0,
            },
          },
        }));
      }
    } catch (error) {
      console.error('[SpiritStones] 获取灵石余额失败:', error);
    }
  },

  fetchMyStall: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/market/stall?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      set({ myStall: data.stall || null });
    } catch (error) {
      console.error('[Stall] 获取我的摊位失败:', error);
    }
  },

  fetchNearbyStalls: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/market/stalls?uid=${encodeURIComponent(uid)}`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data.stalls)) {
        const stalls: Stall[] = data.stalls.map((s: Record<string, unknown>) => ({
          stallId: (s.stall_id as string) || '',
          ownerUid: (s.owner_uid as string) || '',
          ownerName: (s.owner_name as string) || '',
          ownerType: (s.owner_type as 'player' | 'npc') || 'npc',
          stallName: (s.stall_name as string) || '',
          location: (s.location as string) || '',
          items: (Array.isArray(s.items) ? s.items : []).map((i: Record<string, unknown>) => ({
            itemId: (i.item_id as string) || '',
            name: (i.name as string) || '',
            type: (i.type as string) || '',
            description: (i.description as string) || '',
            quantity: (i.quantity as number) || 0,
            price: (i.price as number) || 0,
            isCustomPrice: (i.is_custom_price as boolean) || false,
            grade: (i.grade as string) || undefined,
          })),
          status: (s.status as 'open' | 'closed') || 'closed',
          createdAt: (s.created_at as number) || 0,
          updatedAt: (s.updated_at as number) || 0,
        }));
        set({ nearbyStalls: stalls });
      }
    } catch (error) {
      console.error('[Stall] 获取附近摊位失败:', error);
    }
  },

  createStall: async (stallName, items) => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/market/stall`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, stall_name: stallName, items }),
      });
      if (!response.ok) {
        const data = await response.json();
        console.error('[Stall] 创建摊位失败:', data.error?.message);
        return;
      }
      // 刷新摊位和背包数据
      const { fetchMyStall, fetchInventory } = useGameStore.getState();
      await fetchMyStall();
      await fetchInventory();
    } catch (error) {
      console.error('[Stall] 创建摊位失败:', error);
    }
  },

  closeMyStall: async () => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/market/stall`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid }),
      });
      if (!response.ok) return;
      set({ myStall: null });
      // 刷新背包数据
      const { fetchInventory } = useGameStore.getState();
      await fetchInventory();
    } catch (error) {
      console.error('[Stall] 关闭摊位失败:', error);
    }
  },

  buyFromStall: async (stallId, itemId, quantity) => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const response = await fetch(`${config.API_BASE_URL}/market/trade/buy`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ uid, stall_id: stallId, item_id: itemId, quantity }),
      });
      if (!response.ok) {
        const data = await response.json();
        console.error('[Trade] 购买失败:', data.error?.message);
        return;
      }
      // 刷新灵石、背包、摊位数据
      const { fetchSpiritStones, fetchInventory, fetchMyStall, fetchNearbyStalls } = useGameStore.getState();
      await Promise.all([fetchSpiritStones(), fetchInventory(), fetchMyStall(), fetchNearbyStalls()]);
    } catch (error) {
      console.error('[Trade] 购买失败:', error);
    }
  },

  sellToStall: async (stallId, itemId, quantity, price) => {
    const uid = getOrCreateUserId();
    if (!uid) return;
    try {
      const body: Record<string, unknown> = { uid, stall_id: stallId, item_id: itemId, quantity };
      if (price !== undefined) body.price = price;
      const response = await fetch(`${config.API_BASE_URL}/market/trade/sell`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const data = await response.json();
        console.error('[Trade] 出售失败:', data.error?.message);
        return;
      }
      // 刷新灵石、背包、摊位数据
      const { fetchSpiritStones, fetchInventory, fetchMyStall, fetchNearbyStalls } = useGameStore.getState();
      await Promise.all([fetchSpiritStones(), fetchInventory(), fetchMyStall(), fetchNearbyStalls()]);
    } catch (error) {
      console.error('[Trade] 出售失败:', error);
    }
  },
}));
