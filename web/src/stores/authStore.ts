import { create } from 'zustand';
import { config } from '../config';

interface UserInfo {
  uid: string;
  username: string;
  character_name: string;
}

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, character_name: string) => Promise<void>;
  logout: () => void;
  initAuth: () => void;
  clearError: () => void;
}

const TOKEN_KEY = 'thatman_token';
const USER_KEY = 'thatman_user';

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  initAuth: () => {
    if (typeof window === 'undefined') return;

    const token = localStorage.getItem(TOKEN_KEY);
    const userStr = localStorage.getItem(USER_KEY);

    if (token && userStr) {
      try {
        const user = JSON.parse(userStr) as UserInfo;
        set({
          token,
          user,
          isAuthenticated: true,
        });
      } catch {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
      }
    }
  },

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetch(`${config.API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        const errorMsg = data?.error?.message || data?.message || `登录失败 (${response.status})`;
        set({ isLoading: false, error: errorMsg });
        return;
      }

      const { token, user } = data;

      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));

      set({
        token,
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : '网络错误，请稍后重试',
      });
    }
  },

  register: async (username: string, password: string, character_name: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetch(`${config.API_BASE_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, character_name }),
      });

      const data = await response.json();

      if (!response.ok) {
        const errorMsg = data?.error?.message || data?.message || `注册失败 (${response.status})`;
        set({ isLoading: false, error: errorMsg });
        return;
      }

      const { token, user } = data;

      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));

      set({
        token,
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : '网络错误，请稍后重试',
      });
    }
  },

  logout: () => {
    // 异步调用后端 logout 接口，但不阻塞本地清理
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      fetch(`${config.API_BASE_URL}/auth/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      }).catch(() => {
        // 忽略 logout 接口错误
      });
    }

    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);

    set({
      token: null,
      user: null,
      isAuthenticated: false,
      error: null,
    });
  },

  clearError: () => set({ error: null }),
}));
