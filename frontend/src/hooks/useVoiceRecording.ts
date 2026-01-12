import { useState, useRef, useCallback, useEffect } from 'react';
import { getSupportedMimeType } from '../utils/audio';

interface UseVoiceRecordingOptions {
  silenceThreshold?: number;
  silenceTimeoutMs?: number;
  onRecordingComplete: (blob: Blob) => void;
  onError?: (error: Error) => void;
}

interface UseVoiceRecordingReturn {
  isRecording: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  toggleRecording: () => Promise<void>;
}

export function useVoiceRecording({
  silenceThreshold = 0.01,
  silenceTimeoutMs = 3000,
  onRecordingComplete,
  onError,
}: UseVoiceRecordingOptions): UseVoiceRecordingReturn {
  const [isRecording, setIsRecording] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const silenceStartRef = useRef<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Cleanup function
  const cleanup = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    analyserRef.current = null;
    mediaRecorderRef.current = null;
    silenceStartRef.current = null;
  }, []);

  // Silence detection loop
  const checkSilence = useCallback(() => {
    if (!analyserRef.current || !isRecording) return;

    const buffer = new Float32Array(analyserRef.current.fftSize);
    analyserRef.current.getFloatTimeDomainData(buffer);

    // Calculate RMS
    let sumSquares = 0;
    for (let i = 0; i < buffer.length; i++) {
      sumSquares += buffer[i] * buffer[i];
    }
    const rms = Math.sqrt(sumSquares / buffer.length);

    // Check for silence
    if (rms < silenceThreshold) {
      if (silenceStartRef.current === null) {
        silenceStartRef.current = performance.now();
      } else if (performance.now() - silenceStartRef.current >= silenceTimeoutMs) {
        // Silence timeout reached, stop recording
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          mediaRecorderRef.current.stop();
        }
        return;
      }
    } else {
      // Sound detected, reset silence timer
      silenceStartRef.current = null;
    }

    animationFrameRef.current = requestAnimationFrame(checkSilence);
  }, [isRecording, silenceThreshold, silenceTimeoutMs]);

  const startRecording = useCallback(async () => {
    try {
      // Get microphone permission
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Set up audio context for silence detection
      const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioContextRef.current = new AudioContextClass();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 2048;
      source.connect(analyserRef.current);

      // Set up media recorder
      const mimeType = getSupportedMimeType();
      const options = mimeType ? { mimeType } : undefined;
      const recorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, {
          type: mimeType || 'audio/webm',
        });
        audioChunksRef.current = [];
        setIsRecording(false);
        cleanup();
        onRecordingComplete(blob);
      };

      recorder.start();
      setIsRecording(true);
      silenceStartRef.current = null;

      // Start silence detection
      animationFrameRef.current = requestAnimationFrame(checkSilence);
    } catch (error) {
      cleanup();
      setIsRecording(false);
      if (onError) {
        onError(
          error instanceof Error
            ? error
            : new Error('Failed to start recording')
        );
      }
    }
  }, [cleanup, checkSilence, onRecordingComplete, onError]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const toggleRecording = useCallback(async () => {
    if (isRecording) {
      stopRecording();
    } else {
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  // Cleanup on unmount
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  return {
    isRecording,
    startRecording,
    stopRecording,
    toggleRecording,
  };
}
