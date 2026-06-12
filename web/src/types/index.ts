export interface CharacterState {
  name: string;
  realm: string;
  realmStage: string;
  spiritRoot: string;
  level: number;
  health: number;
  maxHealth: number;
  mana: number;
  maxMana: number;
  spirit: number;
  maxSpirit: number;
  equipment: Equipment[];
  currentLocation: string;
  currentStatus: string;
  birthDate: string;
  lifespan: string;
  clothing: string;
  inventory: InventoryItem[];
  busyState: BusyState | null;
  actionState: ActionState | null;
  lastTimeCost: number;
  karma: number;
  karmaLevel: number;
  karmaTitle: string;
  techniques: Technique[];
  activeBuffs: Buff[];
  titles: Title[];
  injuries: Injury[];
  fatigue: FatigueState;
  mentalState: MentalState;
  spiritStones: SpiritStones;
}

export interface BusyState {
  action: string;
  gameMinutes: number;
  cooldownSeconds: number;
  cooldownRemainingSeconds: number;
  cooldownEndAt: number;
  startedAt: number;
}

export interface TimeModifier {
  source: string;
  factor: number;
  minutes: number;
}

export interface ActionRestrictions {
  forbiddenOperations: string[];
  allowedOperations: string[];
  allowInterrupt: boolean;
  interruptPenalty: string;
}

export interface ActionState {
  isBusy: boolean;
  actionId: string;
  actionName: string;
  baseTimeCost: number;
  finalTimeCost: number;
  modifiers: TimeModifier[];
  gameStartTime: {
    date: string;
    hour: number;
    minute: number;
  };
  cooldownSeconds: number;
  cooldownRemainingSeconds: number;
  cooldownEndAt: number;
  startedAt: number;
  restrictions: ActionRestrictions;
  status: 'active' | 'interrupted' | 'completed';
}

export interface TimeAdvanceInfo {
  advanced_minutes: number;
  reason: string;
  old_time: {
    game_date: string;
    game_year: number;
    game_month: number;
    game_day: number;
    game_hour: number;
    game_minute: number;
    shichen_name: string;
    shichen_period: string;
    shichen_index: number;
  };
  new_time: {
    game_date: string;
    game_year: number;
    game_month: number;
    game_day: number;
    game_hour: number;
    game_minute: number;
    shichen_name: string;
    shichen_period: string;
    shichen_index: number;
    time_ratio: number;
  };
  shichen_changed: boolean;
}

export interface Equipment {
  id: string;
  name: string;
  type: 'weapon' | 'armor' | 'accessory';
  icon: string;
}

export interface InventoryItem {
  id: string;
  name: string;
  type: string;
  description: string;
  quantity: number;
}

export interface WorldState {
  time: string;
  timePeriod: string;
  weather: string;
  weatherDesc: string;
  spiritTide: boolean;
  spiritTideIntensity: number;
  location: string;
  events: WorldEvent[];
  gameDate: string;
  gameHour: number;
  gameMinute: number;
  shichenIndex: number;
}

export interface WorldEvent {
  id: string;
  title: string;
  description: string;
  timestamp: number;
  type: 'normal' | 'important' | 'urgent';
}

export interface KeyEvent {
  id: string;
  uid: string;
  title: string;
  description: string;
  status: 'ongoing' | 'completed';
  sourceMessageId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface HistoryEntry {
  period: string;
  summary: string;
  location: string;
  realmSnapshot: string;
  keyChanges: string[];
  sourceMessageId?: string;
  timestamp: number;
}

export interface CharacterHistory {
  id: string;
  uid: string;
  gameDate: string;
  entries: HistoryEntry[];
  dailySummary: string;
  createdAt: string;
  updatedAt: string;
}

export interface NearbyCharacter {
  id: string;
  name: string;
  type: 'npc' | 'player' | 'monster';
  desc: string;
  currentAction: string;
  avatar?: string;
  uid?: string;           // 真实玩家才有
  isOnline?: boolean;     // 是否在线
  hasStall?: boolean;     // 是否有摊位
  stallId?: string;       // 摊位ID
  stallName?: string;     // 摊位名称
}

export interface OnlinePlayer {
  uid: string;
  characterName: string;
  location: string;
  realm: string;
  realmStage: string;
  status: string;
  lastHeartbeat: number;
  onlineAt: number;
}

export interface ChatContact {
  uid: string;
  characterName: string;
  realm: string;
  realmStage: string;
  lastMessage: string;
  lastMessageTime: number;
  unreadCount: number;
  isOnline: boolean;
}

export interface PrivateMessage {
  id: string;
  fromUid: string;
  fromName: string;
  toUid: string;
  toName: string;
  content: string;
  timestamp: number;
  read: boolean;
}

export interface AreaMessage {
  id: string;
  fromUid: string;
  fromName: string;
  location: string;
  content: string;
  timestamp: number;
}

export interface Entity {
  name: string;
  type: 'character' | 'place' | 'weapon' | 'technique' | 'item';
  desc: string;
  detail?: Record<string, string>;
}

export interface ChatMessage {
  id: string;
  sender: 'player' | 'npc' | 'system';
  senderName?: string;
  senderAvatar?: string;
  content: string;
  timestamp: number;
  type: 'normal' | 'event' | 'system';
  options?: string[];
  actions?: string[];
  parsedJSON?: Record<string, unknown>;
  rawJSON?: string;
  gameDate?: string;
  gameShichen?: string;
  location?: string;
  weather?: string;
  weatherDesc?: string;
  spiritTide?: boolean;
  entities?: Entity[];
}

// 游戏响应JSON结构
export interface GameResponse {
  scene_info: {
    location: string;
    time: string;
    env_effect: string;
  };
  story: string;
  options: string[];
  hint: string;
  panel: string;
}

// 流式解析状态
export interface StreamParseState {
  scene_info?: {
    location?: string;
    time?: string;
    env_effect?: string;
  };
  story: string;
  options: string[];
  hint: string;
  panel: string;
}

export interface KarmaRecord {
  id: string;
  uid: string;
  karmaType: 'grace' | 'enmity' | 'fellowship' | 'friendship' | 'contract' | 'neutral';
  targetId: string;
  targetName: string;
  description: string;
  karmaValue: number;
  resolved: boolean;
  createdAt: string;
}

export interface KarmaBond {
  id: string;
  targetId: string;
  targetName: string;
  bondType: string;
  bondDesc: string;
  totalKarma: number;
  resolved: boolean;
}

// 功法
export interface Technique {
  id: string;
  name: string;
  type: string;         // cultivation(修炼)/combat(战斗)/auxiliary(辅助)
  level: number;        // 修炼层数/境界
  effect: Record<string, unknown>;  // 效果描述
}

// 增益/减益状态
export interface Buff {
  id: string;
  name: string;
  type: 'buff' | 'debuff';
  category: string;     // pill(丹药)/technique(功法)/environment(环境)/injury(伤势)
  effect: Record<string, unknown>;
  duration_minutes: number;  // 持续时间（游戏分钟），-1表示永久
  remaining_minutes: number; // 剩余时间
  applied_at: string;   // 生效时间（游戏日期）
  stackable: boolean;   // 是否可叠加
}

// 称号
export interface Title {
  id: string;
  name: string;
  desc: string;
  source: string;       // 获得来源
  acquired_at: string;  // 获得时间（游戏日期）
  is_equipped: boolean; // 是否装备中
}

// 伤势
export interface Injury {
  id: string;
  name: string;
  severity: 'light' | 'medium' | 'heavy' | 'critical';
  body_part: string;
  health_penalty: number;
  mana_penalty: number;
  spirit_penalty: number;
  recovery_minutes: number;
  remaining_minutes: number;
  caused_at: string;
  cause: string;
}

// 疲劳度
export interface FatigueState {
  value: number;        // 疲劳值 0-100
  level: 'refreshed' | 'normal' | 'tired' | 'exhausted' | 'collapsed';
  recovery_rate: number;
  accumulation_rate: number;
}

// 心神状态
export interface MentalState {
  clarity: number;      // 清明度 0-100
  mood: string;         // calm/focused/anxious/agitated/enlightened
  dao_heart: number;    // 道心稳固度 0-100
}

// 灵石
export interface SpiritStones {
  low: number;      // 下品灵石
  medium: number;   // 中品灵石
  high: number;     // 上品灵石
  top: number;      // 极品灵石
}

// 摊位物品
export interface StallItem {
  itemId: string;
  name: string;
  type: string;
  description: string;
  quantity: number;
  price: number;
  isCustomPrice: boolean;
  grade?: string;
}

// 摊位
export interface Stall {
  stallId: string;
  ownerUid: string;
  ownerName: string;
  ownerType: 'player' | 'npc';
  stallName: string;
  location: string;
  items: StallItem[];
  status: 'open' | 'closed';
  createdAt: number;
  updatedAt: number;
}

