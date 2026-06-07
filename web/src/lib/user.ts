/**
 * 用户管理工具
 * 处理用户ID的获取和认证相关辅助函数
 */

const USER_ID_KEY = 'thatman_user_id'; // 保留兼容

/**
 * 获取或创建用户ID
 * 从 localStorage 读取已登录用户的 uid
 * 如果没有登录用户，返回空字符串（不再自动创建）
 */
export function getOrCreateUserId(): string {
  if (typeof window === 'undefined') {
    return '';
  }

  const userStr = localStorage.getItem('thatman_user');
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      return user.uid || '';
    } catch {
      return '';
    }
  }
  return '';
}

/**
 * 获取当前用户ID（不创建新的）
 */
export function getUserId(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const userStr = localStorage.getItem('thatman_user');
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      return user.uid || null;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * 设置用户ID（保留兼容）
 */
export function setUserId(userId: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.setItem(USER_ID_KEY, userId);
}

/**
 * 清除用户ID（保留兼容）
 */
export function clearUserId(): void {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.removeItem(USER_ID_KEY);
}

/**
 * 获取请求头（携带 Bearer token）
 */
export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('thatman_token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
}

/**
 * 获取认证 token
 */
export function getToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return localStorage.getItem('thatman_token');
}

/**
 * 判断是否已登录
 */
export function isAuthenticated(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  return !!localStorage.getItem('thatman_token') && !!localStorage.getItem('thatman_user');
}
