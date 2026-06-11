import { X, Scale, Link2 } from 'lucide-react';
import { useGameStore } from '../stores/gameStore';
import type { KarmaRecord, KarmaBond } from '../types';

interface KarmaDialogProps {
  open: boolean;
  onClose: () => void;
}

// 因果类型 -> 显示名称映射
const KARMA_TYPE_LABELS: Record<string, string> = {
  grace: '恩情',
  enmity: '仇怨',
  fellowship: '同门',
  friendship: '知己',
  contract: '契约',
  neutral: '陌路',
};

// 因果类型 -> 颜色映射
const KARMA_TYPE_COLORS: Record<string, string> = {
  grace: '#C9A962',
  enmity: '#E74C3C',
  fellowship: '#4ECDC4',
  friendship: '#5ab8b8',
  contract: '#9B59B6',
  neutral: '#7F8C8D',
};

// 业力等级配置
const KARMA_LEVEL_CONFIG: Record<number, { title: string; color: string; glow: string }> = {
  5: { title: '功德圆满', color: '#FFD700', glow: 'shadow-[#FFD700]/30' },
  4: { title: '善行卓著', color: '#4CAF50', glow: 'shadow-[#4CAF50]/30' },
  3: { title: '因果清净', color: '#B0BEC5', glow: 'shadow-[#B0BEC5]/20' },
  2: { title: '业障缠身', color: '#FF9800', glow: 'shadow-[#FF9800]/30' },
  1: { title: '罪孽深重', color: '#E74C3C', glow: 'shadow-[#E74C3C]/30' },
};

function getKarmaLevelConfig(level: number) {
  return KARMA_LEVEL_CONFIG[level] ?? KARMA_LEVEL_CONFIG[3];
}

function getKarmaValueColor(karma: number): string {
  if (karma > 0) return '#FFD700';
  if (karma < 0) return '#E74C3C';
  return '#B0BEC5';
}

function formatTime(isoString: string): string {
  if (!isoString) return '';
  try {
    const date = new Date(isoString);
    const month = date.getMonth() + 1;
    const day = date.getDate();
    const hour = date.getHours().toString().padStart(2, '0');
    const minute = date.getMinutes().toString().padStart(2, '0');
    return `${month}月${day}日 ${hour}:${minute}`;
  } catch {
    return '';
  }
}

export function KarmaDialog({ open, onClose }: KarmaDialogProps) {
  const { character, karmaRecords, karmaBonds } = useGameStore();
  const { karma, karmaLevel, karmaTitle } = character;

  if (!open) return null;

  const levelConfig = getKarmaLevelConfig(karmaLevel);
  const valueColor = getKarmaValueColor(karma);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-lg mx-4 rounded-xl border border-[#2d5a5a]/50 shadow-2xl shadow-black/50 overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, #1A1A2E 0%, #0D0D0D 100%)',
          fontFamily: 'Noto Serif SC, serif',
        }}
      >
        {/* Top ASCII border */}
        <div
          className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden"
          style={{ fontFamily: 'monospace' }}
        >
          ╔══════════════════════════════════════════════════════════════╗
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#2d5a5a]/30">
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5" style={{ color: '#C9A962' }} />
            <h2
              className="text-lg font-bold tracking-wider"
              style={{ color: '#C9A962' }}
            >
              因果业力
            </h2>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-md bg-[#1a2f2f] border border-[#2d5a5a]/50 text-[#5a7a7a] hover:text-[#C9A962] hover:border-[#C9A962]/50 transition-colors duration-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
          {/* Karma Value & Level */}
          <div className="flex items-center justify-center gap-6 mb-5">
            {/* Karma Value */}
            <div className="flex flex-col items-center">
              <span className="text-xs mb-1" style={{ color: '#7F8C8D' }}>业力值</span>
              <div
                className={`text-3xl font-bold px-4 py-2 rounded-lg shadow-lg ${levelConfig.glow}`}
                style={{
                  color: valueColor,
                  textShadow: `0 0 12px ${valueColor}60`,
                  background: `${valueColor}10`,
                }}
              >
                {karma > 0 ? `+${karma}` : karma}
              </div>
            </div>

            {/* Divider */}
            <div className="w-px h-12 bg-[#2d5a5a]/30" />

            {/* Karma Level & Title */}
            <div className="flex flex-col items-center">
              <span className="text-xs mb-1" style={{ color: '#7F8C8D' }}>善恶称号</span>
              <div
                className="text-lg font-bold px-4 py-2 rounded-lg"
                style={{
                  color: levelConfig.color,
                  textShadow: `0 0 8px ${levelConfig.color}40`,
                  background: `${levelConfig.color}10`,
                }}
              >
                {karmaTitle || levelConfig.title}
              </div>
            </div>
          </div>

          {/* Karma Bar */}
          <div className="mb-5 px-2">
            <div className="flex items-center justify-between text-[10px] mb-1" style={{ color: '#5a7a7a' }}>
              <span>罪孽深重</span>
              <span>因果清净</span>
              <span>功德圆满</span>
            </div>
            <div className="relative h-2 bg-[#1a2f2f] rounded-full overflow-hidden border border-[#2d5a5a]/30">
              <div
                className="absolute top-0 left-1/2 h-full w-px bg-[#5a7a7a]/50"
              />
              <div
                className="absolute top-0 h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(Math.max((karma + 100) / 200 * 100, 2), 100)}%`,
                  background: `linear-gradient(90deg, ${valueColor}80, ${valueColor})`,
                  boxShadow: `0 0 8px ${valueColor}60`,
                  left: karma >= 0 ? '50%' : undefined,
                  right: karma < 0 ? '50%' : undefined,
                }}
              />
            </div>
          </div>

          {/* Section separator */}
          <div
            className="text-[#2d5a5a]/50 text-[10px] leading-none mb-3 select-none overflow-hidden whitespace-nowrap"
            style={{ fontFamily: 'monospace' }}
          >
            ◈ ───────────────────────────────────────────────────────── ◈
          </div>

          {/* Karma Records Timeline */}
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-2">
              <Scale className="w-4 h-4" style={{ color: '#4ECDC4' }} />
              <span
                className="text-sm font-medium tracking-wide"
                style={{ color: '#4ECDC4' }}
              >
                因果记录
              </span>
              {karmaRecords.length > 0 && (
                <span className="text-[#7F8C8D] text-xs">({karmaRecords.length})</span>
              )}
            </div>

            {karmaRecords.length === 0 ? (
              <div className="text-center py-6">
                <span className="text-3xl opacity-30 block mb-2">⚖️</span>
                <p className="text-[#7F8C8D] text-sm">尚无因果记录</p>
                <p className="text-[#7F8C8D]/60 text-xs mt-1">与世间生灵结缘，方有因果纠缠</p>
              </div>
            ) : (
              <div className="space-y-2">
                {karmaRecords.map((record: KarmaRecord) => (
                  <KarmaRecordCard key={record.id} record={record} />
                ))}
              </div>
            )}
          </div>

          {/* Section separator */}
          {karmaBonds.length > 0 && (
            <div
              className="text-[#2d5a5a]/50 text-[10px] leading-none mb-3 select-none overflow-hidden whitespace-nowrap"
              style={{ fontFamily: 'monospace' }}
            >
              ◈ ───────────────────────────────────────────────────────── ◈
            </div>
          )}

          {/* Karma Bonds */}
          {karmaBonds.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Link2 className="w-4 h-4" style={{ color: '#9B59B6' }} />
                <span
                  className="text-sm font-medium tracking-wide"
                  style={{ color: '#9B59B6' }}
                >
                  因果羁绊
                </span>
                <span className="text-[#7F8C8D] text-xs">({karmaBonds.length})</span>
              </div>
              <div className="space-y-2">
                {karmaBonds.map((bond: KarmaBond) => (
                  <KarmaBondCard key={bond.id} bond={bond} />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-2.5 border-t border-[#2d5a5a]/30 bg-[#0D0D0D]/50">
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: '#7F8C8D' }}>
              因果记录 {karmaRecords.length} 条
            </span>
            <span className="text-xs" style={{ color: '#7F8C8D' }}>
              羁绊 {karmaBonds.length} 条
            </span>
          </div>
        </div>

        {/* Bottom ASCII border */}
        <div
          className="text-center text-[#2d5a5a]/60 text-xs leading-none py-2 select-none overflow-hidden"
          style={{ fontFamily: 'monospace' }}
        >
          ╚══════════════════════════════════════════════════════════════╝
        </div>
      </div>
    </div>
  );
}

function KarmaRecordCard({ record }: { record: KarmaRecord }) {
  const typeLabel = KARMA_TYPE_LABELS[record.karmaType] ?? '未知';
  const typeColor = KARMA_TYPE_COLORS[record.karmaType] ?? '#7F8C8D';
  const isPositive = record.karmaValue > 0;

  return (
    <div className="flex items-start gap-3 px-3 py-2.5 rounded-lg transition-colors duration-200 hover:bg-[#2d5a5a]/15 cursor-default">
      {/* Timeline dot */}
      <div className="mt-1.5 shrink-0">
        <div
          className="w-2 h-2 rounded-full"
          style={{
            backgroundColor: typeColor,
            boxShadow: `0 0 6px ${typeColor}60`,
          }}
        />
      </div>

      {/* Record info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="text-sm font-medium truncate"
            style={{ color: '#E8E8E8' }}
          >
            {record.targetName || '未知'}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded shrink-0"
            style={{
              color: typeColor,
              background: `${typeColor}15`,
            }}
          >
            {typeLabel}
          </span>
          <span
            className="text-xs font-medium shrink-0 ml-auto"
            style={{
              color: isPositive ? '#FFD700' : '#E74C3C',
            }}
          >
            {isPositive ? `功德 +${record.karmaValue}` : `业障 ${record.karmaValue}`}
          </span>
        </div>
        {record.description && (
          <p
            className="text-xs mt-1 leading-relaxed line-clamp-2"
            style={{ color: '#7F8C8D' }}
          >
            {record.description}
          </p>
        )}
        {record.createdAt && (
          <p className="text-[10px] mt-1" style={{ color: '#5a7a7a' }}>
            {formatTime(record.createdAt)}
          </p>
        )}
      </div>
    </div>
  );
}

function KarmaBondCard({ bond }: { bond: KarmaBond }) {
  const isPositive = bond.totalKarma > 0;
  const bondColor = isPositive ? '#C9A962' : '#E74C3C';

  return (
    <div className="flex items-start gap-3 px-3 py-2.5 rounded-lg transition-colors duration-200 hover:bg-[#2d5a5a]/15 cursor-default">
      {/* Bond icon */}
      <div className="mt-0.5 shrink-0">
        <Link2 className="w-4 h-4" style={{ color: bondColor }} />
      </div>

      {/* Bond info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="text-sm font-medium truncate"
            style={{ color: '#E8E8E8' }}
          >
            {bond.targetName || '未知'}
          </span>
          {bond.bondType && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded shrink-0"
              style={{
                color: bondColor,
                background: `${bondColor}15`,
              }}
            >
              {bond.bondType}
            </span>
          )}
          {bond.resolved && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#7F8C8D]/15 text-[#7F8C8D] shrink-0">
              已了结
            </span>
          )}
        </div>
        {bond.bondDesc && (
          <p
            className="text-xs mt-1 leading-relaxed line-clamp-2"
            style={{ color: '#7F8C8D' }}
          >
            {bond.bondDesc}
          </p>
        )}
      </div>
    </div>
  );
}
