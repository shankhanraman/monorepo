import { useCallback, useEffect, useRef, useState } from 'react';

/** Sets the position and starts playback. A rejected `play()` (autoplay policy) is ignored: the position is still set. */
function seekAndPlay(audio: HTMLAudioElement, seconds: number) {
  try {
    // Before metadata is loaded this sets the default playback start position (HTML spec), so it also works early.
    audio.currentTime = seconds;
  } catch {
    // very old browsers throw before metadata; play() below still starts the audio
  }
  try {
    audio.play().catch(() => {
      /* blocked by the browser's autoplay policy; the user can press play */
    });
  } catch {
    /* play() threw synchronously (non-standard); nothing else to do */
  }
}

/**
 * Drives a native `<audio>` element (attach `audioRef`) and returns `seek(seconds)`, which sets `currentTime` and plays.
 * `startSeconds` (the `?t=` of the page URL) is only used on mount; null means "start at the beginning, don't play".
 * Mirrors useYouTubePlayer so both players plug into the same time-based view.
 */
export function useAudioPlayer(startSeconds: number | null) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const startRef = useRef(startSeconds);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    const start = startRef.current;
    startRef.current = null; // once (StrictMode runs effects twice in development)
    if (audio && start !== null) seekAndPlay(audio, start);
  }, []);

  const seek = useCallback((seconds: number) => {
    const audio = audioRef.current;
    if (audio) seekAndPlay(audio, seconds);
  }, []);

  const onError = useCallback(() => setError('Could not load the audio file.'), []);
  const onCanPlay = useCallback(() => setError(null), []);

  return { audioRef, seek, error, onError, onCanPlay };
}
