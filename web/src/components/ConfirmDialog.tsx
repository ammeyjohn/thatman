import { Trash2, X } from 'lucide-react';

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  messageCount?: number;
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title = '删除消息',
  message,
  confirmText = '删除',
  cancelText = '取消',
  messageCount = 1,
}: ConfirmDialogProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative bg-[#1a1a1f] border border-[#3d3d45] rounded-2xl shadow-2xl max-w-md w-full mx-4 p-6">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-[#5a5a6a] hover:text-[#a0a0b0] transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
            <Trash2 className="w-5 h-5 text-red-400" />
          </div>
          <h3 className="text-lg font-semibold text-[#e8e8f0]">{title}</h3>
        </div>

        {/* Message */}
        <p className="text-[#a0a0b0] text-sm leading-relaxed mb-6">
          {message}
        </p>

        {/* Buttons */}
        <div className="flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-[#a0a0b0] hover:text-[#e8e8f0] bg-[#2a2a35] hover:bg-[#3a3a45] rounded-lg transition-all duration-200"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm text-white bg-red-500 hover:bg-red-600 rounded-lg transition-all duration-200 shadow-lg shadow-red-500/20"
          >
            {messageCount > 1 ? `删除 ${messageCount} 条消息` : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
