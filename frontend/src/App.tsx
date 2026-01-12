import { useEffect, useCallback } from 'react';
import { SessionProvider, useSession } from './context/SessionContext';
import { NeuralBackground } from './components/background/NeuralBackground';
import { Card } from './components/layout/Card';
import { TipsBox, AvaAvatar } from './components/tips/TipsBox';
import { IntakeForm } from './components/intake/IntakeForm';
import { ChatWindow } from './components/chat/ChatWindow';
import { SessionPill } from './components/status/SessionPill';
import { VoiceToggle } from './components/voice/VoiceToggle';
import { useVoiceRecording } from './hooks/useVoiceRecording';
import { useAudioPlayback } from './hooks/useAudioPlayback';

function AppContent() {
  const {
    messages,
    status,
    isAgentResponding,
    agentVoiceEnabled,
    callEnded,
    sessionId,
    startSession,
    sendMessage,
    sendVoiceMessage,
    setAgentVoiceEnabled,
    addMessage,
    resetSession,
    pendingAudioRef,
  } = useSession();

  const { playAudio, unlockAudio } = useAudioPlayback({ enabled: agentVoiceEnabled });

  const handleRecordingComplete = useCallback(
    async (blob: Blob) => {
      await sendVoiceMessage(blob);
    },
    [sendVoiceMessage]
  );

  const handleRecordingError = useCallback(
    (error: Error) => {
      addMessage({
        role: 'meta',
        content: `Microphone error: ${error.message}`,
      });
    },
    [addMessage]
  );

  const { isRecording, toggleRecording } = useVoiceRecording({
    onRecordingComplete: handleRecordingComplete,
    onError: handleRecordingError,
  });

  // Play pending audio when agent responds
  useEffect(() => {
    if (pendingAudioRef.current && !isAgentResponding) {
      const audio = pendingAudioRef.current;
      pendingAudioRef.current = null;
      playAudio(audio).catch(() => {
        // Ignore playback failures (autoplay restrictions handled by unlock).
      });
    }
  }, [isAgentResponding, pendingAudioRef, playAudio]);

  const isChatDisabled = !sessionId || callEnded || status === 'thinking';
  const isThinking = status === 'thinking';

  const handleSendText = useCallback(
    (text: string) => {
      unlockAudio().catch(() => {
        // Ignore unlock errors; playback will try again on next gesture.
      });
      sendMessage(text);
    },
    [sendMessage, unlockAudio]
  );

  const handleMicClick = useCallback(async () => {
    try {
      await unlockAudio();
    } catch {
      // Ignore unlock errors; playback will try again on next gesture.
    }
    await toggleRecording();
  }, [toggleRecording, unlockAudio]);

  return (
    <div className="min-h-screen gradient-bg flex flex-col">
      {/* Neural Network Background - fires when Ava is thinking */}
      <NeuralBackground isAgentResponding={isThinking} />

      {/* Main Content */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-3xl space-y-6">
          {/* Header */}
          <header className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="md:hidden">
                <AvaAvatar className="w-12 h-12" />
              </div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-semibold text-clinai-text">
                  ClinAI Voice Agent
                </h1>
                <p className="text-sm sm:text-base text-clinai-text-dim">
                  AI Healthcare Receptionist
                </p>
              </div>
            </div>
          </header>

          {/* Main Card */}
          <Card className="p-6 sm:p-8">
            {/* Tips Box - Show when session not active */}
            {!sessionId && (
              <div className="animate-fade-in mb-8">
                <TipsBox />
              </div>
            )}

            {/* Intake Form - Show when session not active */}
            {!sessionId && (
              <div className="animate-fade-in">
                <IntakeForm onSubmit={startSession} disabled={status === 'thinking'} />
              </div>
            )}

            {/* Chat Window - Show when session active */}
            {sessionId && (
              <div className="animate-fade-in">
                  <ChatWindow
                    messages={messages}
                    isTyping={isThinking}
                  onSendText={handleSendText}
                  onMicClick={handleMicClick}
                  disabled={isChatDisabled}
                  isRecording={isRecording}
                />
              </div>
            )}

            {/* Status Bar */}
            <div className="flex items-center justify-between mt-6 pt-6 border-t border-clinai-border">
              <div className="flex items-center gap-3">
                <SessionPill status={status} />
                {status === 'ended' && (
                  <button
                    type="button"
                    onClick={resetSession}
                    className="btn-primary px-4 py-2 text-sm"
                  >
                    New chat
                  </button>
                )}
              </div>
              <VoiceToggle
                enabled={agentVoiceEnabled}
                onChange={setAgentVoiceEnabled}
              />
            </div>
          </Card>

          {/* Footer */}
          <footer className="text-center">
            <p className="text-sm text-clinai-text-dim">
              Powered by ClinAI &middot; For demo purposes only
            </p>
          </footer>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <SessionProvider>
      <AppContent />
    </SessionProvider>
  );
}

export default App;
