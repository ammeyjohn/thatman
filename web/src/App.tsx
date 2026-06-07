import { useState, useEffect } from 'react';
import { CharacterPanel } from './components/CharacterPanel';
import { WorldEventPanel } from './components/WorldEventPanel';
import { ChatArea } from './components/ChatArea';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { useChatStore } from './stores/chatStore';
import { useGameStore } from './stores/gameStore';
import { config } from './config';

const LEFT_COLLAPSED_KEY = 'thatman:leftCollapsed';
const RIGHT_COLLAPSED_KEY = 'thatman:rightCollapsed';

function getInitialCollapsed(key: string, defaultValue: boolean): boolean {
  try {
    const stored = localStorage.getItem(key);
    return stored !== null ? stored === 'true' : defaultValue;
  } catch {
    return defaultValue;
  }
}

function App() {
  const [leftCollapsed, setLeftCollapsed] = useState(() =>
    getInitialCollapsed(LEFT_COLLAPSED_KEY, false)
  );
  const [rightCollapsed, setRightCollapsed] = useState(() =>
    getInitialCollapsed(RIGHT_COLLAPSED_KEY, false)
  );

  // 页面初始化时加载聊天历史和用户信息
  useEffect(() => {
    const loadInitialData = async () => {
      const { loadUserInfo } = useGameStore.getState();
      const { loadChatHistory } = useChatStore.getState();
      await Promise.all([loadUserInfo(), loadChatHistory()]);

      // 检查是否需要触发 GM 引导教程（新用户首次登录）
      await triggerTutorialIfNeeded();
    };
    loadInitialData();
  }, []);

  // 新用户 GM 引导教程
  const triggerTutorialIfNeeded = async () => {
    const TUTORIAL_SHOWN_KEY = 'thatman_tutorial_shown';
    const userStr = localStorage.getItem('thatman_user');

    if (!userStr) return;

    // 检查是否已经展示过教程
    try {
      const user = JSON.parse(userStr);
      const tutorialKey = `${TUTORIAL_SHOWN_KEY}_${user.uid}`;
      if (localStorage.getItem(tutorialKey)) return;

      // 调用引导教程接口
      const response = await fetch(`${config.API_BASE_URL}/gm/tutorial`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid: user.uid }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.dialog) {
          // 以系统消息形式展示引导内容
          const { addMessage } = useChatStore.getState();
          addMessage({
            sender: 'system',
            senderName: '引路仙灵',
            content: data.dialog,
            type: 'system',
          });
        }
        // 标记教程已展示
        localStorage.setItem(tutorialKey, 'true');
      }
    } catch (error) {
      console.error('引导教程加载失败:', error);
    }
  };

  useEffect(() => {
    localStorage.setItem(LEFT_COLLAPSED_KEY, String(leftCollapsed));
  }, [leftCollapsed]);

  useEffect(() => {
    localStorage.setItem(RIGHT_COLLAPSED_KEY, String(rightCollapsed));
  }, [rightCollapsed]);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#0a0a0f] flex">
      {/* Left Panel */}
      <div
        className={`bg-[#0d1f1f] relative flex flex-col transition-all duration-300 ease-in-out ${
          leftCollapsed ? 'w-0 opacity-0 overflow-hidden' : 'w-[280px] opacity-100'
        }`}
      >
        <CharacterPanel />
      </div>

      {/* Left Collapse/Expand Handle */}
      <div className="relative flex items-center">
        <button
          onClick={() => setLeftCollapsed(!leftCollapsed)}
          className={`absolute z-50 flex items-center justify-center w-6 h-12 rounded-r-md bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#c9a227] hover:border-[#c9a227]/50 transition-all duration-300 cursor-pointer ${
            leftCollapsed ? 'left-0' : 'left-0'
          }`}
          style={{ top: '50%', transform: 'translateY(-50%)' }}
          title={leftCollapsed ? '展开左侧面板' : '缩进左侧面板'}
        >
          {leftCollapsed ? (
            <PanelLeftOpen className="w-4 h-4" />
          ) : (
            <PanelLeftClose className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Center Panel - Chat Area */}
      <div className="flex-1 min-w-0 flex flex-col h-full">
        <ChatArea />
      </div>

      {/* Right Collapse/Expand Handle */}
      <div className="relative flex items-center">
        <button
          onClick={() => setRightCollapsed(!rightCollapsed)}
          className={`absolute z-50 flex items-center justify-center w-6 h-12 rounded-l-md bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#c9a227] hover:border-[#c9a227]/50 transition-all duration-300 cursor-pointer ${
            rightCollapsed ? 'right-0' : 'right-0'
          }`}
          style={{ top: '50%', transform: 'translateY(-50%)' }}
          title={rightCollapsed ? '展开右侧面板' : '缩进右侧面板'}
        >
          {rightCollapsed ? (
            <PanelRightOpen className="w-4 h-4" />
          ) : (
            <PanelRightClose className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Right Panel */}
      <div
        className={`bg-[#0d1f1f] relative flex flex-col transition-all duration-300 ease-in-out ${
          rightCollapsed ? 'w-0 opacity-0 overflow-hidden' : 'w-[280px] opacity-100'
        }`}
      >
        <WorldEventPanel />
      </div>
    </div>
  );
}

export default App;
