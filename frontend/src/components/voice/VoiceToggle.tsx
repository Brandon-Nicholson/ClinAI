interface VoiceToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}

export function VoiceToggle({ enabled, onChange }: VoiceToggleProps) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <span className="text-xs font-medium text-clinai-text-dim uppercase tracking-wide">
        Agent Voice
      </span>
      <div className="relative">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only peer"
        />
        <div
          className={`
            w-9 h-5 rounded-full transition-colors duration-200
            ${enabled ? 'bg-clinai-accent' : 'bg-clinai-border-light'}
          `}
        />
        <div
          className={`
            absolute top-0.5 left-0.5 w-4 h-4 rounded-full
            bg-white shadow-sm transition-transform duration-200
            ${enabled ? 'translate-x-4' : 'translate-x-0'}
          `}
        />
      </div>
    </label>
  );
}
