interface PatientToggleProps {
  isReturning: boolean;
  onChange: (isReturning: boolean) => void;
  disabled?: boolean;
}

export function PatientToggle({
  isReturning,
  onChange,
  disabled = false,
}: PatientToggleProps) {
  return (
    <label
      className={`
        flex items-center gap-3 cursor-pointer select-none
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <div className="relative">
        <input
          type="checkbox"
          checked={isReturning}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className="sr-only peer"
        />
        <div
          className={`
            w-5 h-5 rounded border-2 transition-all duration-200
            flex items-center justify-center
            ${
              isReturning
                ? 'bg-clinai-accent border-clinai-accent'
                : 'bg-transparent border-clinai-border-light'
            }
          `}
        >
          {isReturning && (
            <svg
              className="w-3 h-3 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={3}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5 13l4 4L19 7"
              />
            </svg>
          )}
        </div>
      </div>
      <span className="text-sm text-clinai-text-muted">
        I'm a returning patient
      </span>
    </label>
  );
}
