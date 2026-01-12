import { useCallback, useRef, useEffect } from 'react';
import { base64ToArrayBuffer } from '../utils/audio';

interface UseAudioPlaybackOptions {
  enabled: boolean;
}

export function useAudioPlayback({ enabled }: UseAudioPlaybackOptions) {
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      const AudioContextClass =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      audioContextRef.current = new AudioContextClass();
    }
    return audioContextRef.current;
  }, []);

  const cleanup = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.onended = null;
      sourceRef.current.disconnect();
      try {
        sourceRef.current.stop();
      } catch {
        // Ignore stop errors when already finished.
      }
      sourceRef.current = null;
    }
  }, []);

  const unlockAudio = useCallback(async () => {
    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
    }
  }, [getAudioContext]);

  const playAudio = useCallback(
    async (base64: string): Promise<void> => {
      if (!enabled) return;

      // Cleanup previous audio
      cleanup();

      const context = getAudioContext();
      if (context.state === 'suspended') {
        await context.resume();
      }

      const audioBuffer = await context.decodeAudioData(
        base64ToArrayBuffer(base64)
      );

      return new Promise((resolve) => {
        const source = context.createBufferSource();
        sourceRef.current = source;
        source.buffer = audioBuffer;
        source.connect(context.destination);
        source.onended = () => {
          cleanup();
          resolve();
        };
        source.start(0);
      });
    },
    [enabled, cleanup, getAudioContext]
  );

  const stopAudio = useCallback(() => {
    cleanup();
  }, [cleanup]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanup();
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
    };
  }, [cleanup]);

  return {
    playAudio,
    stopAudio,
    unlockAudio,
  };
}
