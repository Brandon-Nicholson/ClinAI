import { useCallback, useRef, useEffect } from 'react';
import { createAudioUrl } from '../utils/audio';

interface UseAudioPlaybackOptions {
  enabled: boolean;
}

export function useAudioPlayback({ enabled }: UseAudioPlaybackOptions) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const playAudio = useCallback(
    async (base64: string): Promise<void> => {
      if (!enabled) return;

      // Cleanup previous audio
      cleanup();

      return new Promise((resolve, reject) => {
        try {
          const url = createAudioUrl(base64);
          urlRef.current = url;

          const audio = new Audio(url);
          audioRef.current = audio;

          audio.onended = () => {
            cleanup();
            resolve();
          };

          audio.onerror = () => {
            cleanup();
            reject(new Error('Failed to play audio'));
          };

          audio.play().catch((error) => {
            cleanup();
            reject(error);
          });
        } catch (error) {
          cleanup();
          reject(error);
        }
      });
    },
    [enabled, cleanup]
  );

  const stopAudio = useCallback(() => {
    cleanup();
  }, [cleanup]);

  // Cleanup on unmount
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  return {
    playAudio,
    stopAudio,
  };
}
