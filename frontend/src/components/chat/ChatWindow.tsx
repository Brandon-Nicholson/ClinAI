import { MessageList } from './MessageList';
import { Composer } from './Composer';
import type { Message } from '../../types';

interface ChatWindowProps {
  messages: Message[];
  isTyping: boolean;
  onSendText: (text: string) => void;
  onMicClick: () => void;
  disabled?: boolean;
  isRecording?: boolean;
}

export function ChatWindow({
  messages,
  isTyping,
  onSendText,
  onMicClick,
  disabled = false,
  isRecording = false,
}: ChatWindowProps) {
  return (
    <div className="flex flex-col h-[400px] sm:h-[480px] bg-clinai-bg/50 rounded-xl border border-clinai-border overflow-hidden">
      <MessageList messages={messages} isTyping={isTyping} />
      <Composer
        onSendText={onSendText}
        onMicClick={onMicClick}
        disabled={disabled}
        isRecording={isRecording}
      />
    </div>
  );
}
