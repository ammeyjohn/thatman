import { useState } from 'react';
import type { ChatMessage as ChatMessageType } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Pencil, Trash2, RefreshCw, Check } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { ConfirmDialog } from './ConfirmDialog';

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessageItem({ message }: ChatMessageProps) {
  const { deleteMessage, editMessage, regenerateMessage } = useChatStore();
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);
  const [copied, setCopied] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('复制失败:', err);
    }
  };

  const handleDeleteClick = () => {
    setShowDeleteDialog(true);
  };

  const handleConfirmDelete = () => {
    deleteMessage(message.id);
    setShowDeleteDialog(false);
  };

  const handleCloseDialog = () => {
    setShowDeleteDialog(false);
  };

  const handleEdit = () => {
    if (isEditing) {
      // 保存编辑
      editMessage(message.id, editContent);
      setIsEditing(false);
    } else {
      // 开始编辑
      setEditContent(message.content);
      setIsEditing(true);
    }
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleEdit();
    }
    if (e.key === 'Escape') {
      setIsEditing(false);
      setEditContent(message.content);
    }
  };

  const handleRegenerate = () => {
    regenerateMessage(message.id);
  };

  if (message.type === 'system') {
    return (
      <div className="flex justify-center my-4">
        <div className="px-4 py-2 bg-[#2d5a5a]/20 border border-[#2d5a5a]/40 rounded-full">
          <span className="text-[#a0c0c0] text-sm">{message.content}</span>
        </div>
      </div>
    );
  }

  if (message.type === 'event') {
    return (
      <div className="flex justify-center my-4">
        <div className="px-4 py-3 bg-gradient-to-r from-[#c9a227]/20 via-[#c9a227]/10 to-[#c9a227]/20 border border-[#c9a227]/40 rounded-lg max-w-[80%]">
          <div className="text-[#c9a227] text-sm text-center">{message.content}</div>
        </div>
      </div>
    );
  }

  const isPlayer = message.sender === 'player';

  // 用户消息按钮：复制、编辑、删除
  const playerButtons = (
    <div className={`flex items-center gap-1 mt-2 ${isPlayer ? 'justify-end' : 'justify-start'}`}>
      <button
        onClick={handleCopy}
        className="p-1.5 text-[#5a7a7a] hover:text-[#a0c0c0] hover:bg-[#2d5a5a]/30 rounded transition-all duration-200"
        title={copied ? '已复制' : '复制'}
      >
        {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
      </button>
      <button
        onClick={handleEdit}
        className="p-1.5 text-[#5a7a7a] hover:text-[#a0c0c0] hover:bg-[#2d5a5a]/30 rounded transition-all duration-200"
        title={isEditing ? '保存' : '编辑'}
      >
        {isEditing ? <Check className="w-4 h-4" /> : <Pencil className="w-4 h-4" />}
      </button>
      <button
        onClick={handleDeleteClick}
        className="p-1.5 text-[#5a7a7a] hover:text-red-400 hover:bg-red-500/10 rounded transition-all duration-200"
        title="删除"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );

  // AI 消息按钮：复制、编辑、重新生成、删除
  const npcButtons = (
    <div className={`flex items-center gap-1 mt-2 ${isPlayer ? 'justify-end' : 'justify-start'}`}>
      <button
        onClick={handleCopy}
        className="p-1.5 text-[#5a7a7a] hover:text-[#a0c0c0] hover:bg-[#2d5a5a]/30 rounded transition-all duration-200"
        title={copied ? '已复制' : '复制'}
      >
        {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
      </button>
      <button
        onClick={handleEdit}
        className="p-1.5 text-[#5a7a7a] hover:text-[#a0c0c0] hover:bg-[#2d5a5a]/30 rounded transition-all duration-200"
        title={isEditing ? '保存' : '编辑'}
      >
        {isEditing ? <Check className="w-4 h-4" /> : <Pencil className="w-4 h-4" />}
      </button>
      <button
        onClick={handleRegenerate}
        className="p-1.5 text-[#5a7a7a] hover:text-[#c9a227] hover:bg-[#c9a227]/10 rounded transition-all duration-200"
        title="重新生成"
      >
        <RefreshCw className="w-4 h-4" />
      </button>
      <button
        onClick={handleDeleteClick}
        className="p-1.5 text-[#5a7a7a] hover:text-red-400 hover:bg-red-500/10 rounded transition-all duration-200"
        title="删除"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );

  // 准备删除对话框的文案
  const isPlayerMessage = message.sender === 'player';
  const deleteDialogMessage = isPlayerMessage
    ? '这将删除 2 条消息，包括：1 条用户消息和 1 条助手回复。此操作无法撤销。'
    : '确定要删除这条消息吗？此操作无法撤销。';

  return (
    <>
      <div className={`flex ${isPlayer ? 'justify-end' : 'justify-start'} mb-4`}>
        <div className={`flex items-start gap-3 max-w-[80%] ${isPlayer ? 'flex-row-reverse' : 'flex-row'}`}>
          {/* Avatar */}
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
              isPlayer
                ? 'bg-gradient-to-br from-[#3d7a7a] to-[#2d5a5a] border border-[#3d9a9a]'
                : 'bg-gradient-to-br from-[#c9a227] to-[#a08020] border border-[#f0d878]'
            }`}
          >
            <span className="text-lg">{isPlayer ? '👤' : message.senderAvatar || '🧙'}</span>
          </div>

          {/* Message Content */}
          <div className={`flex flex-col ${isPlayer ? 'items-end' : 'items-start'}`}>
            {/* Sender Name */}
            {!isPlayer && message.senderName && (
              <span className="text-xs text-[#a0c0c0] mb-1">{message.senderName}</span>
            )}

            {/* Message Bubble */}
            <div
              className={`px-4 py-3 rounded-2xl ${
                isPlayer
                  ? 'bg-gradient-to-br from-[#2d5a5a] to-[#1a3a3a] border border-[#3d7a7a]/50 rounded-tr-sm'
                  : 'bg-gradient-to-br from-[#1a2f2f] to-[#0d1f1f] border border-[#2d5a5a]/50 rounded-tl-sm'
              }`}
            >
              {isEditing ? (
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  onKeyDown={handleEditKeyDown}
                  className="w-full min-w-[200px] bg-transparent text-[#e8e4dc] text-sm resize-none outline-none border-0 focus:ring-0"
                  rows={3}
                  autoFocus
                />
              ) : (
                <div className="markdown-body text-[#e8e4dc] text-sm leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              )}
            </div>

            {/* Timestamp */}
            <span className="text-[10px] text-[#5a7a7a] mt-1">{formatTime(message.timestamp)}</span>

            {/* Action Buttons */}
            {isPlayer ? playerButtons : npcButtons}
          </div>
        </div>
      </div>

      {/* Delete Confirm Dialog */}
      <ConfirmDialog
        isOpen={showDeleteDialog}
        onClose={handleCloseDialog}
        onConfirm={handleConfirmDelete}
        message={deleteDialogMessage}
        messageCount={isPlayerMessage ? 2 : 1}
      />
    </>
  );
}
