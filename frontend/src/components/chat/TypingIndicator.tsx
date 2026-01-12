export function TypingIndicator() {
  return (
    <div className="flex justify-start animate-message-in">
      <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-clinai-bg-secondary border border-clinai-border">
        <div className="flex items-center gap-1">
          <span
            className="w-2 h-2 rounded-full bg-clinai-text-muted animate-dot-bounce"
            style={{ animationDelay: '0ms' }}
          />
          <span
            className="w-2 h-2 rounded-full bg-clinai-text-muted animate-dot-bounce"
            style={{ animationDelay: '150ms' }}
          />
          <span
            className="w-2 h-2 rounded-full bg-clinai-text-muted animate-dot-bounce"
            style={{ animationDelay: '300ms' }}
          />
        </div>
      </div>
    </div>
  );
}
