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

