import { CharacterPanel } from './components/CharacterPanel';
import { WorldEventPanel } from './components/WorldEventPanel';
import { ChatArea } from './components/ChatArea';

function App() {
  return (
    <div className="h-screen w-screen overflow-hidden bg-[#0a0a0f] flex">
      {/* Left Panel - Character Status */}
      <CharacterPanel />

      {/* Center Panel - Chat Area */}
      <ChatArea />

      {/* Right Panel - World Events */}
      <WorldEventPanel />
    </div>
  );
}

export default App;
