/**
 * 用户管理工具
 * 处理用户ID的生成、存储和获取
 */

const USER_ID_KEY = 'thatman_user_id';

/**
 * 生成随机用户ID
 */
function generateUserId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 10);
  return `user_${timestamp}_${random}`;
}

/**
 * 获取或创建用户ID
 * 从 localStorage 读取，如果不存在则创建并保存
 */
export function getOrCreateUserId(): string {
  if (typeof window === 'undefined') {
    return '';
  }

  let userId = localStorage.getItem(USER_ID_KEY);

  if (!userId) {
    userId = generateUserId();
    localStorage.setItem(USER_ID_KEY, userId);
    console.log('[User] 创建新用户ID:', userId);
  } else {
    console.log('[User] 使用已有用户ID:', userId);
  }

  return userId;
}

/**
 * 获取当前用户ID（不创建新的）
 */
export function getUserId(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return localStorage.getItem(USER_ID_KEY);
}

/**
 * 设置用户ID
 */
export function setUserId(userId: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.setItem(USER_ID_KEY, userId);
}

/**
 * 清除用户ID
 */
export function clearUserId(): void {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.removeItem(USER_ID_KEY);
}

/**
 * 获取请求头（包含用户ID）
 */
export function getAuthHeaders(): Record<string, string> {
  const userId = getOrCreateUserId();
  return {
    'Content-Type': 'application/json',
    'X-User-Id': userId,
  };
}
