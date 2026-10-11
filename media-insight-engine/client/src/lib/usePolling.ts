import { useEffect, useRef } from 'react';

/**
 * Calls `fn` every `ms` while `enabled`. The next call is scheduled only after the previous one settles.
 * Pauses while the tab is hidden (`document.visibilityState`) and fires immediately when it becomes visible again.
 */
export function usePolling(fn: () => Promise<unknown> | void, ms: number, enabled: boolean): void {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let paused = false;
    let timer: number | undefined;

    const tick = async () => {
      if (stopped) return;
      if (document.visibilityState === 'hidden') {
        paused = true;
        return;
      }
      try {
        await fnRef.current();
      } catch {
        // callers handle their own errors; keep polling
      }
      if (!stopped) timer = window.setTimeout(tick, ms);
    };
    const onVisibility = () => {
      if (paused && document.visibilityState === 'visible') {
        paused = false;
        void tick();
      }
    };

    timer = window.setTimeout(tick, ms);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [enabled, ms]);
}
