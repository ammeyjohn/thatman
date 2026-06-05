import { createBrowserRouter, Navigate } from 'react-router-dom';
import Home from '@/pages/Home';

// 定义路由配置
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Home />,
  },
  {
    path: '/about',
    element: <div className="text-center text-xl p-8">About Page - Coming Soon</div>,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);

export default router;
