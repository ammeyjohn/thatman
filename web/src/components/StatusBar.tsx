interface StatusBarProps {
  label: string;
  current: number;
  max: number;
  color: string;
  icon: string;
}

export function StatusBar({ label, current, max, color, icon }: StatusBarProps) {
  const percentage = Math.min(100, Math.max(0, (current / max) * 100));

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-base">{icon}</span>
          <span className="text-xs text-[#a0c0c0] font-medium">{label}</span>
        </div>
        <span className="text-xs text-[#a0c0c0]">
          {current}/{max}
        </span>
      </div>
      <div className="h-2 bg-[#1a2f2f] rounded-full overflow-hidden border border-[#2d5a5a]/30">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{
            width: `${percentage}%`,
            backgroundColor: color,
            boxShadow: `0 0 8px ${color}50`,
          }}
        />
      </div>
    </div>
  );
}
