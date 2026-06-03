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
}

export interface Equipment {
  id: string;
  name: string;
  type: 'weapon' | 'armor' | 'accessory';
  icon: string;
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
}

export interface WorldEvent {
  id: string;
  title: string;
  description: string;
  timestamp: number;
  type: 'normal' | 'important' | 'urgent';
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
