import { useState } from 'react';
import { CharacterPanel } from './components/CharacterPanel';
import { WorldEventPanel } from './components/WorldEventPanel';
import { ChatArea } from './components/ChatArea';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react';

function App() {
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#0a0a0f] flex">
      {/* Left Panel */}
      <div
        className={`relative flex flex-col transition-all duration-300 ease-in-out ${
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
      <ChatArea />

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
        className={`relative flex flex-col transition-all duration-300 ease-in-out ${
          rightCollapsed ? 'w-0 opacity-0 overflow-hidden' : 'w-[280px] opacity-100'
        }`}
      >
        <WorldEventPanel />
      </div>
    </div>
  );
}

export default App;
