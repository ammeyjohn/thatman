import { createBrowserRouter, Navigate } from 'react-router-dom';
import Home from '@/pages/Home';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import App from '@/App';
import { isAuthenticated } from '@/lib/user';

// 鉴权守卫组件：已登录才能访问
function AuthGuard({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

// 游客守卫组件：未登录才能访问（登录/注册页面）
function GuestGuard({ children }: { children: React.ReactNode }) {
  if (isAuthenticated()) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

// 定义路由配置
export const router = createBrowserRouter([
  {
    path: '/login',
    element: <GuestGuard><LoginPage /></GuestGuard>,
  },
  {
    path: '/register',
    element: <GuestGuard><RegisterPage /></GuestGuard>,
  },
  {
    path: '/',
    element: <AuthGuard><App /></AuthGuard>,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);

export default router;
