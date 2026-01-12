import type { SessionStatus } from '../../types';

interface SessionPillProps {
  status: SessionStatus;
}

const statusConfig: Record<
  SessionStatus,
  { label: string; dotClass: string }
> = {
  idle: { label: 'Ready', dotClass: 'bg-clinai-text-dim' },
  active: { label: 'Session Active', dotClass: 'bg-clinai-success animate-dot-pulse' },
  thinking: { label: 'Agent is thinking...', dotClass: 'bg-clinai-accent animate-dot-pulse' },
  error: { label: 'Error', dotClass: 'bg-clinai-error' },
  ended: { label: 'Call Ended', dotClass: 'bg-clinai-text-dim' },
};

export function SessionPill({ status }: SessionPillProps) {
  const config = statusConfig[status];

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-clinai-bg-secondary border border-clinai-border">
      <span className={`w-2 h-2 rounded-full ${config.dotClass}`} />
      <span className="text-xs font-medium text-clinai-text-muted uppercase tracking-wide">
        {config.label}
      </span>
    </div>
  );
}
