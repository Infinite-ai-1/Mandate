import { useCallback, useEffect, useState } from "react";
import { cached, request } from "./api";

export function useResource<T>(path: string | null, version = 0) {
  const [state, setState] = useState<{
    path: string | null;
    data?: T;
    error?: string;
    loading: boolean;
  }>({ path, data: path ? cached<T>(path) : undefined, loading: !!path });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!path) {
      setState({ path: null, loading: false });
      return;
    }
    const controller = new AbortController();
    let active = true;
    setState({ path, data: cached<T>(path), loading: true });
    request<T>(path, undefined, controller.signal)
      .then((data) => {
        if (active) setState({ path, data, loading: false });
      })
      .catch((error) => {
        if (active)
          setState({
            path,
            data: cached<T>(path),
            loading: false,
            error:
              error instanceof Error ? error.message : "Unable to load data.",
          });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, version, attempt]);
  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  // Never leak the previous charity's result while a new effect starts.
  return {
    ...(state.path === path
      ? state
      : { path, data: path ? cached<T>(path) : undefined, loading: !!path }),
    retry,
  };
}
