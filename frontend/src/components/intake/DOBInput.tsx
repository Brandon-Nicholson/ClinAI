interface DOBInputProps {
  month: string;
  day: string;
  year: string;
  onMonthChange: (value: string) => void;
  onDayChange: (value: string) => void;
  onYearChange: (value: string) => void;
  disabled?: boolean;
}

export function DOBInput({
  month,
  day,
  year,
  onMonthChange,
  onDayChange,
  onYearChange,
  disabled = false,
}: DOBInputProps) {
  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-clinai-text-dim uppercase tracking-wider">
        Date of Birth
      </label>
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="MM"
          value={month}
          onChange={(e) => {
            const val = e.target.value.replace(/\D/g, '').slice(0, 2);
            onMonthChange(val);
          }}
          disabled={disabled}
          maxLength={2}
          className="input-field w-16 text-center"
        />
        <input
          type="text"
          placeholder="DD"
          value={day}
          onChange={(e) => {
            const val = e.target.value.replace(/\D/g, '').slice(0, 2);
            onDayChange(val);
          }}
          disabled={disabled}
          maxLength={2}
          className="input-field w-16 text-center"
        />
        <input
          type="text"
          placeholder="YYYY"
          value={year}
          onChange={(e) => {
            const val = e.target.value.replace(/\D/g, '').slice(0, 4);
            onYearChange(val);
          }}
          disabled={disabled}
          maxLength={4}
          className="input-field w-24 text-center"
        />
      </div>
    </div>
  );
}
