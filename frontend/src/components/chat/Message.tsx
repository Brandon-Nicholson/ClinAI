import type { Message as MessageType } from '../../types';

interface MessageProps {
  message: MessageType;
}

export function Message({ message }: MessageProps) {
  const { role, content } = message;

  if (role === 'meta') {
    return (
      <div className="flex justify-center py-2 animate-message-in">
        <span className="text-xs text-clinai-text-dim italic px-4 py-1.5 rounded-full bg-clinai-bg-secondary/50">
          {content}
        </span>
      </div>
    );
  }

  const isUser = role === 'user';

  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-message-in`}
    >
      <div
        className={`
          max-w-[85%] sm:max-w-[75%] px-4 py-3 rounded-2xl
          ${
            isUser
              ? 'bg-gradient-to-br from-clinai-accent to-clinai-accent-hover text-white rounded-br-md'
              : 'bg-clinai-bg-secondary border border-clinai-border text-clinai-text rounded-bl-md'
          }
        `}
      >
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
