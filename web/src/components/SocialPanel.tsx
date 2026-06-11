import React, { useState, useRef, useEffect } from 'react';
import { useSocialStore } from '../stores/socialStore';
import { useGameStore } from '../stores/gameStore';
import type { OnlinePlayer } from '../types';

const SocialPanel: React.FC = () => {
  const {
    isSocialPanelOpen,
    setSocialPanelOpen,
    activeTab,
    setActiveTab,
    contacts,
    privateMessages,
    areaMessages,
    selectedContactUid,
    sendPrivateMessage,
    selectContact,
    loadContacts,
    loadAreaMessages,
    friends,
    friendRequests,
    sendFriendRequest,
    acceptFriendRequest,
    rejectFriendRequest,
    deleteFriend,
    loadFriends,
    loadFriendRequests,
    teamInfo,
    createTeam,
    leaveTeam,
    disbandTeam,
    inviteTeamMember,
  } = useSocialStore();

  const { onlinePlayers, character } = useGameStore();
  const [messageInput, setMessageInput] = useState('');
  const [friendUidInput, setFriendUidInput] = useState('');
  const [inviteUidInput, setInviteUidInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [privateMessages, areaMessages]);

  // 打开时加载数据
  useEffect(() => {
    if (isSocialPanelOpen) {
      loadContacts();
      if (activeTab === 'friends') {
        loadFriends();
        loadFriendRequests();
      }
      if (activeTab === 'area' && character.currentLocation) {
        loadAreaMessages(character.currentLocation);
      }
    }
  }, [isSocialPanelOpen, activeTab]);

  const handleSendMessage = async () => {
    if (!messageInput.trim() || !selectedContactUid) return;
    await sendPrivateMessage(selectedContactUid, messageInput.trim());
    setMessageInput('');
  };

  const handleSendAreaMessage = async () => {
    if (!messageInput.trim()) return;
    const { sendAreaMessage } = useSocialStore.getState();
    await sendAreaMessage(messageInput.trim());
    setMessageInput('');
  };

  const handleAddFriend = async () => {
    if (!friendUidInput.trim()) return;
    await sendFriendRequest(friendUidInput.trim());
    setFriendUidInput('');
  };

  const handleInviteTeamMember = async () => {
    if (!inviteUidInput.trim()) return;
    await inviteTeamMember(inviteUidInput.trim());
    setInviteUidInput('');
  };

  const getSelectedContactName = () => {
    const contact = contacts.find(c => c.uid === selectedContactUid);
    return contact?.characterName || '';
  };

  if (!isSocialPanelOpen) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-96 bg-gray-900/95 border-l border-gray-700 flex flex-col z-50 shadow-2xl">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <h2 className="text-white text-lg font-bold">社交</h2>
        <button
          onClick={() => setSocialPanelOpen(false)}
          className="text-gray-400 hover:text-white text-xl"
        >
          ✕
        </button>
      </div>

      {/* 在线人数 */}
      <div className="px-4 py-2 bg-gray-800/50 text-gray-400 text-sm">
        在线: {onlinePlayers.length} 人
      </div>

      {/* Tab 切换 */}
      <div className="flex border-b border-gray-700">
        {[
          { key: 'contacts' as const, label: '聊天' },
          { key: 'area' as const, label: '区域' },
          { key: 'friends' as const, label: '好友' },
          { key: 'team' as const, label: '队伍' },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'text-amber-400 border-b-2 border-amber-400'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* 聊天 Tab */}
        {activeTab === 'contacts' && (
          <>
            {/* 联系人列表 */}
            <div className="w-full border-b border-gray-700 max-h-40 overflow-y-auto">
              {contacts.length === 0 && onlinePlayers.length === 0 && (
                <div className="p-3 text-gray-500 text-sm text-center">暂无联系人</div>
              )}
              {onlinePlayers.map((p: OnlinePlayer) => (
                <button
                  key={p.uid}
                  onClick={() => selectContact(p.uid)}
                  className={`w-full px-4 py-2 text-left hover:bg-gray-800 flex items-center gap-2 ${
                    selectedContactUid === p.uid ? 'bg-gray-800' : ''
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-green-400" />
                  <span className="text-white text-sm">{p.characterName}</span>
                  <span className="text-gray-500 text-xs">{p.realm}{p.realmStage}</span>
                </button>
              ))}
              {contacts.map(c => (
                <button
                  key={c.uid}
                  onClick={() => selectContact(c.uid)}
                  className={`w-full px-4 py-2 text-left hover:bg-gray-800 flex items-center gap-2 ${
                    selectedContactUid === c.uid ? 'bg-gray-800' : ''
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-gray-500" />
                  <span className="text-gray-300 text-sm">{c.characterName}</span>
                  {c.unreadCount > 0 && (
                    <span className="ml-auto bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">
                      {c.unreadCount}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* 聊天窗口 */}
            <div className="flex-1 flex flex-col">
              {selectedContactUid ? (
                <>
                  <div className="px-4 py-2 bg-gray-800/30 text-amber-400 text-sm font-medium border-b border-gray-700">
                    与 {getSelectedContactName()} 的对话
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 space-y-2">
                    {privateMessages.map(msg => (
                      <div
                        key={msg.id}
                        className={`flex ${msg.fromUid === selectedContactUid ? 'justify-start' : 'justify-end'}`}
                      >
                        <div
                          className={`max-w-[80%] px-3 py-2 rounded-lg text-sm ${
                            msg.fromUid === selectedContactUid
                              ? 'bg-gray-700 text-gray-200'
                              : 'bg-amber-600/80 text-white'
                          }`}
                        >
                          <div>{msg.content}</div>
                          <div className="text-xs opacity-50 mt-1">
                            {new Date(msg.timestamp).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                  <div className="p-3 border-t border-gray-700 flex gap-2">
                    <input
                      type="text"
                      value={messageInput}
                      onChange={e => setMessageInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                      placeholder="输入消息..."
                      className="flex-1 bg-gray-800 text-white px-3 py-2 rounded-lg text-sm outline-none focus:ring-1 focus:ring-amber-400"
                    />
                    <button
                      onClick={handleSendMessage}
                      className="bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm"
                    >
                      发送
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
                  选择联系人开始聊天
                </div>
              )}
            </div>
          </>
        )}

        {/* 区域 Tab */}
        {activeTab === 'area' && (
          <>
            <div className="px-4 py-2 bg-gray-800/30 text-amber-400 text-sm font-medium border-b border-gray-700">
              {character.currentLocation || '未知区域'}
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {areaMessages.map(msg => (
                <div key={msg.id} className="px-3 py-2">
                  <span className="text-amber-400 text-sm font-medium">{msg.fromName}: </span>
                  <span className="text-gray-200 text-sm">{msg.content}</span>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              ))}
              {areaMessages.length === 0 && (
                <div className="text-gray-500 text-sm text-center py-8">暂无区域消息</div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="p-3 border-t border-gray-700 flex gap-2">
              <input
                type="text"
                value={messageInput}
                onChange={e => setMessageInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendAreaMessage()}
                placeholder="发送区域消息..."
                className="flex-1 bg-gray-800 text-white px-3 py-2 rounded-lg text-sm outline-none focus:ring-1 focus:ring-amber-400"
              />
              <button
                onClick={handleSendAreaMessage}
                className="bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm"
              >
                发送
              </button>
            </div>
          </>
        )}

        {/* 好友 Tab */}
        {activeTab === 'friends' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* 添加好友 */}
            <div className="flex gap-2">
              <input
                type="text"
                value={friendUidInput}
                onChange={e => setFriendUidInput(e.target.value)}
                placeholder="输入玩家 UID 添加好友"
                className="flex-1 bg-gray-800 text-white px-3 py-2 rounded-lg text-sm outline-none focus:ring-1 focus:ring-amber-400"
              />
              <button
                onClick={handleAddFriend}
                className="bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm"
              >
                添加
              </button>
            </div>

            {/* 好友申请 */}
            {friendRequests.length > 0 && (
              <div>
                <h3 className="text-gray-400 text-xs font-medium mb-2">待处理申请</h3>
                {friendRequests.map((req, idx) => (
                  <div key={idx} className="flex items-center justify-between py-2 px-3 bg-gray-800 rounded-lg mb-1">
                    <span className="text-white text-sm">{req.from_name || req.from_uid}</span>
                    <div className="flex gap-2">
                      <button
                        onClick={() => acceptFriendRequest(req.from_uid as string)}
                        className="text-green-400 text-xs hover:text-green-300"
                      >
                        接受
                      </button>
                      <button
                        onClick={() => rejectFriendRequest(req.from_uid as string)}
                        className="text-red-400 text-xs hover:text-red-300"
                      >
                        拒绝
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 好友列表 */}
            <div>
              <h3 className="text-gray-400 text-xs font-medium mb-2">好友列表</h3>
              {friends.length === 0 ? (
                <div className="text-gray-500 text-sm text-center py-4">暂无好友</div>
              ) : (
                friends.map(f => (
                  <div key={f.uid} className="flex items-center justify-between py-2 px-3 bg-gray-800 rounded-lg mb-1">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${f.isOnline ? 'bg-green-400' : 'bg-gray-500'}`} />
                      <span className="text-white text-sm">{f.characterName}</span>
                    </div>
                    <button
                      onClick={() => deleteFriend(f.uid)}
                      className="text-red-400 text-xs hover:text-red-300"
                    >
                      删除
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* 队伍 Tab */}
        {activeTab === 'team' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {teamInfo && (teamInfo as Record<string, unknown>).team_id ? (
              <>
                <div className="bg-gray-800 rounded-lg p-4">
                  <h3 className="text-amber-400 text-sm font-medium mb-2">
                    队伍 {(teamInfo as Record<string, unknown>).team_id as string}
                  </h3>
                  <div className="space-y-1">
                    {((teamInfo as Record<string, unknown>).members as Array<Record<string, unknown>>)?.map((m, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-sm">
                        <span className={m.uid === (teamInfo as Record<string, unknown>).leader_uid ? 'text-amber-400' : 'text-gray-300'}>
                          {m.name as string}
                        </span>
                        {m.uid === (teamInfo as Record<string, unknown>).leader_uid && (
                          <span className="text-xs text-amber-400">(队长)</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => leaveTeam()}
                    className="flex-1 bg-gray-700 hover:bg-gray-600 text-white py-2 rounded-lg text-sm"
                  >
                    离开队伍
                  </button>
                  {(teamInfo as Record<string, unknown>).leader_uid === character.currentLocation && (
                    <button
                      onClick={() => disbandTeam()}
                      className="flex-1 bg-red-600/80 hover:bg-red-500 text-white py-2 rounded-lg text-sm"
                    >
                      解散队伍
                    </button>
                  )}
                </div>
                {/* 邀请成员 */}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={inviteUidInput}
                    onChange={e => setInviteUidInput(e.target.value)}
                    placeholder="输入玩家 UID 邀请"
                    className="flex-1 bg-gray-800 text-white px-3 py-2 rounded-lg text-sm outline-none focus:ring-1 focus:ring-amber-400"
                  />
                  <button
                    onClick={handleInviteTeamMember}
                    className="bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm"
                  >
                    邀请
                  </button>
                </div>
              </>
            ) : (
              <div className="text-center py-8">
                <div className="text-gray-500 text-sm mb-4">你还没有加入队伍</div>
                <button
                  onClick={() => createTeam()}
                  className="bg-amber-600 hover:bg-amber-500 text-white px-6 py-2 rounded-lg text-sm"
                >
                  创建队伍
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default SocialPanel;
