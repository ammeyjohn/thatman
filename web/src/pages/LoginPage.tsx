import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, isLoading, error, clearError } = useAuthStore();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await login(username, password);
    if (useAuthStore.getState().isAuthenticated) {
      navigate('/');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0D0D0D] px-4">
      <div className="w-full max-w-sm">
        {/* ASCII 装饰 */}
        <div className="text-center text-[#7F8C8D] text-sm tracking-widest mb-2 font-mono">
          ◈ ─────────── ◈
        </div>

        {/* 标题 */}
        <h1 className="text-center text-3xl font-bold text-[#C9A962] mb-1 font-mono tracking-wider">
          青墟灵修志
        </h1>
        <p className="text-center text-sm text-[#7F8C8D] mb-8 font-mono">
          入道之门
        </p>

        {/* 表单卡片 */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* 用户名 */}
          <div>
            <input
              type="text"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (error) clearError();
              }}
              placeholder="请输入名号"
              required
              className="w-full px-4 py-3 rounded-md bg-[#1A1A2E] border border-[#2D2424] text-[#E8E8E8] placeholder-[#7F8C8D] font-mono text-sm focus:outline-none focus:border-[#4ECDC4] transition-colors duration-200"
            />
          </div>

          {/* 密码 */}
          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (error) clearError();
              }}
              placeholder="请输入密令"
              required
              className="w-full px-4 py-3 rounded-md bg-[#1A1A2E] border border-[#2D2424] text-[#E8E8E8] placeholder-[#7F8C8D] font-mono text-sm focus:outline-none focus:border-[#4ECDC4] transition-colors duration-200"
            />
          </div>

          {/* 错误提示 */}
          {error && (
            <p className="text-[#E74C3C] text-xs font-mono text-center">
              {error}
            </p>
          )}

          {/* 登录按钮 */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 rounded-md bg-[#4ECDC4] text-[#0D0D0D] font-mono font-bold text-sm tracking-wider hover:bg-[#6FE4DB] disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200 cursor-pointer"
          >
            {isLoading ? '验证中...' : '踏入青墟'}
          </button>
        </form>

        {/* 底部链接 */}
        <p className="text-center mt-6 font-mono text-sm">
          <Link
            to="/register"
            className="text-[#4ECDC4] hover:text-[#6FE4DB] transition-colors duration-200"
          >
            尚无道号？前往注册 →
          </Link>
        </p>

        {/* 底部装饰 */}
        <div className="text-center text-[#7F8C8D] text-sm tracking-widest mt-8 font-mono">
          ◈ ─────────── ◈
        </div>
      </div>
    </div>
  );
}
