import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import type { Message, SessionState, SessionStatus, StartSessionRequest } from '../types';
import * as api from '../api/clinai';

interface SessionContextValue extends SessionState {
  startSession: (data: StartSessionRequest) => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  sendVoiceMessage: (audioBlob: Blob) => Promise<void>;
  setAgentVoiceEnabled: (enabled: boolean) => void;
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void;
  setStatus: (status: SessionStatus) => void;
  setIsAgentResponding: (responding: boolean) => void;
  resetSession: () => void;
  pendingAudioRef: React.MutableRefObject<string | null>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<SessionStatus>('idle');
  const [isAgentResponding, setIsAgentResponding] = useState(false);
  const [agentVoiceEnabled, setAgentVoiceEnabled] = useState(true);
  const [callEnded, setCallEnded] = useState(false);
  const pendingAudioRef = useRef<string | null>(null);

  const addMessage = useCallback(
    (message: Omit<Message, 'id' | 'timestamp'>) => {
      const newMessage: Message = {
        ...message,
        id: crypto.randomUUID(),
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, newMessage]);
    },
    []
  );

  const startSession = useCallback(
    async (data: StartSessionRequest) => {
      setStatus('thinking');
      setIsAgentResponding(true);

      try {
        const response = await api.startSession(data);
        setSessionId(response.session_id);
        setStatus('active');
        setCallEnded(false);

        // Add intro messages
        for (const msg of response.messages) {
          addMessage({
            role: 'agent',
            content: msg.content,
          });
        }

        // Store audio for playback
        if (response.audio_b64) {
          pendingAudioRef.current = response.audio_b64;
        }
      } catch (error) {
        setStatus('error');
        addMessage({
          role: 'meta',
          content:
            error instanceof Error
              ? error.message
              : 'Failed to start session',
        });
      } finally {
        setIsAgentResponding(false);
      }
    },
    [addMessage]
  );

  const sendMessage = useCallback(
    async (text: string) => {
      if (!sessionId || !text.trim()) return;

      addMessage({ role: 'user', content: text });
      setStatus('thinking');
      setIsAgentResponding(true);

      try {
        const response = await api.sendTurn({
          session_id: sessionId,
          user_input: text,
        });

        addMessage({ role: 'agent', content: response.agent_message });

        if (response.audio_b64) {
          pendingAudioRef.current = response.audio_b64;
        }

        if (response.end_call) {
          setCallEnded(true);
          setStatus('ended');
          addMessage({
            role: 'meta',
            content: 'Call ended. Thank you for using ClinAI!',
          });
        } else {
          setStatus('active');
        }
      } catch (error) {
        setStatus('error');
        addMessage({
          role: 'meta',
          content: 'Failed to send message. Please try again.',
        });
      } finally {
        setIsAgentResponding(false);
      }
    },
    [sessionId, addMessage]
  );

  const sendVoiceMessage = useCallback(
    async (audioBlob: Blob) => {
      if (!sessionId) return;

      setStatus('thinking');
      setIsAgentResponding(true);

      try {
        const response = await api.sendVoiceTurn(sessionId, audioBlob);

        // Add user transcript
        if (response.user_transcript) {
          addMessage({ role: 'user', content: response.user_transcript });
        }

        addMessage({ role: 'agent', content: response.agent_message });

        if (response.audio_b64) {
          pendingAudioRef.current = response.audio_b64;
        }

        if (response.end_call) {
          setCallEnded(true);
          setStatus('ended');
          addMessage({
            role: 'meta',
            content: 'Call ended. Thank you for using ClinAI!',
          });
        } else {
          setStatus('active');
        }
      } catch (error) {
        setStatus('error');
        addMessage({
          role: 'meta',
          content: 'Failed to process voice message. Please try again.',
        });
      } finally {
        setIsAgentResponding(false);
      }
    },
    [sessionId, addMessage]
  );

  const resetSession = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setStatus('idle');
    setIsAgentResponding(false);
    setCallEnded(false);
    pendingAudioRef.current = null;
  }, []);

  const value: SessionContextValue = {
    sessionId,
    messages,
    status,
    isAgentResponding,
    agentVoiceEnabled,
    callEnded,
    startSession,
    sendMessage,
    sendVoiceMessage,
    setAgentVoiceEnabled,
    addMessage,
    setStatus,
    setIsAgentResponding,
    resetSession,
    pendingAudioRef,
  };

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
}
