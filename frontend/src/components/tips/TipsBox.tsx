const AVA_IMAGE = 'https://cdn-icons-png.flaticon.com/512/4712/4712027.png';

const TIPS = [
  'Clinic information',
  'Scheduling appointments',
  'Rescheduling',
  'Canceling',
  'Prescription refills',
  'Transferring to a human',
];

interface TipsBoxProps {
  showAva?: boolean;
}

export function TipsBox({ showAva = true }: TipsBoxProps) {
  return (
    <div className="flex items-start gap-4 p-4 sm:p-5 rounded-xl bg-clinai-bg-secondary/50 border border-clinai-border">
      <div className="flex-1">
        <h3 className="text-sm font-semibold text-clinai-text-muted uppercase tracking-wider mb-3">
          Ava can help with
        </h3>
        <ul className="space-y-1.5">
          {TIPS.map((tip) => (
            <li
              key={tip}
              className="flex items-center gap-2 text-sm text-clinai-text-muted"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-clinai-accent flex-shrink-0" />
              {tip}
            </li>
          ))}
        </ul>
      </div>
      {showAva && (
        <div className="hidden md:block flex-shrink-0">
          <img
            src={AVA_IMAGE}
            alt="Ava assistant"
            className="w-20 h-20 rounded-xl object-cover opacity-90"
          />
        </div>
      )}
    </div>
  );
}

export function AvaAvatar({ className = '' }: { className?: string }) {
  return (
    <img
      src={AVA_IMAGE}
      alt="Ava"
      className={`rounded-full object-cover ${className}`}
    />
  );
}
