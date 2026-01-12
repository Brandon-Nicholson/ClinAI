import React, { useState, useCallback } from 'react';

interface ComposerProps {
  onSendText: (text: string) => void;
  onMicClick: () => void;
  disabled?: boolean;
  isRecording?: boolean;
}

export function Composer({
  onSendText,
  onMicClick,
  disabled = false,
  isRecording = false,
}: ComposerProps) {
  const [text, setText] = useState('');

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!text.trim() || disabled) return;
      onSendText(text.trim());
      setText('');
    },
    [text, disabled, onSendText]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (text.trim() && !disabled) {
          onSendText(text.trim());
          setText('');
        }
      }
    },
    [text, disabled, onSendText]
  );

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 px-4 py-3 border-t border-clinai-border"
    >
      {/* Mic Button */}
      <button
        type="button"
        onClick={onMicClick}
        disabled={disabled}
        className={`
          btn-icon relative
          ${isRecording ? 'text-clinai-error border-clinai-error' : ''}
        `}
        aria-label={isRecording ? 'Stop recording' : 'Start recording'}
      >
        {isRecording && (
          <span className="absolute inset-0 rounded-full bg-clinai-error/20 animate-mic-pulse" />
        )}
        <svg
          className="w-5 h-5 relative z-10"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
          />
        </svg>
      </button>

      {/* Text Input */}
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message..."
        disabled={disabled}
        className="flex-1 input-field py-2.5"
      />

      {/* Send Button */}
      <button
        type="submit"
        disabled={!text.trim() || disabled}
        className="btn-icon bg-clinai-accent border-clinai-accent text-white
                   hover:bg-clinai-accent-hover hover:border-clinai-accent-hover
                   disabled:bg-clinai-bg-secondary disabled:border-clinai-border disabled:text-clinai-text-dim"
        aria-label="Send message"
      >
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
          />
        </svg>
      </button>
    </form>
  );
}
