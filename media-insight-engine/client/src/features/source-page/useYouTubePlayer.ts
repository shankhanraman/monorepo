import { useCallback, useEffect, useRef, useState } from 'react';

// Minimal typings for the parts of the YouTube IFrame API we use.
interface YTPlayer {
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  destroy(): void;
}
interface YTPlayerOptions {
  videoId: string;
  width?: string | number;
  height?: string | number;
  playerVars?: Record<string, string | number>;
  events?: { onReady?: (event: { target: YTPlayer }) => void };
}
interface YTNamespace {
  Player: new (element: HTMLElement, options: YTPlayerOptions) => YTPlayer;
}
declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<YTNamespace> | null = null;

/** Loads https://www.youtube.com/iframe_api once per page. */
function loadYouTubeApi(): Promise<YTNamespace> {
  if (apiPromise) return apiPromise;
  apiPromise = new Promise<YTNamespace>((resolve, reject) => {
    if (window.YT?.Player) {
      resolve(window.YT);
      return;
    }
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (window.YT) resolve(window.YT);
    };
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    script.onerror = () => {
      apiPromise = null;
      script.remove();
      reject(new Error('Could not load the YouTube player.'));
    };
    document.head.appendChild(script);
  });
  return apiPromise;
}

/**
 * Embeds a YouTube player into `containerRef` and returns `seek(seconds)`.
 * `startSeconds` is only used for the first load (the `?t=` of the page URL).
 */
export function useYouTubePlayer(videoId: string | null, startSeconds: number) {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const startRef = useRef(startSeconds);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!videoId || !container) return;
    let cancelled = false;
    let player: YTPlayer | null = null;
    // The API replaces this element with an iframe, so give it a node React does not manage.
    const mount = document.createElement('div');
    container.appendChild(mount);

    loadYouTubeApi().then(
      (YT) => {
        if (cancelled) return;
        player = new YT.Player(mount, {
          videoId,
          width: '100%',
          height: '100%',
          playerVars: { start: Math.max(0, Math.floor(startRef.current)), playsinline: 1, rel: 0 },
          events: {
            onReady: ({ target }) => {
              if (cancelled) return;
              playerRef.current = target;
              const pending = pendingSeekRef.current;
              pendingSeekRef.current = null;
              if (pending !== null) {
                target.seekTo(pending, true);
                target.playVideo();
              }
            },
          },
        });
      },
      (e: Error) => {
        if (!cancelled) setError(e.message);
      },
    );

    return () => {
      cancelled = true;
      player?.destroy();
      playerRef.current = null;
      container.replaceChildren();
    };
  }, [videoId]);

  const seek = useCallback((seconds: number) => {
    const player = playerRef.current;
    if (player) {
      player.seekTo(seconds, true);
      player.playVideo();
    } else {
      pendingSeekRef.current = seconds; // applied once the player is ready
    }
  }, []);

  return { containerRef, seek, error };
}
