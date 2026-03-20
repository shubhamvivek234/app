import { useEffect } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export const usePostStatusStream = (onUpdate) => {
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token || !BACKEND_URL) return;

    let controller = new AbortController();
    let retryTimeout = null;
    let retryDelay = 2000;

    const connect = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/stream/post-updates`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });

        if (!response.ok) return;
        retryDelay = 2000; // reset on success

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop(); // keep incomplete line

          for (const line of lines) {
            if (line.startsWith('data: ') && line.trim() !== 'data: connected') {
              try {
                const data = JSON.parse(line.slice(6));
                onUpdate(data);
              } catch (_) {
                // ignore parse errors for malformed SSE lines
              }
            }
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') return;
      }

      // Reconnect with exponential backoff (max 30s)
      retryDelay = Math.min(retryDelay * 2, 30000);
      retryTimeout = setTimeout(connect, retryDelay);
    };

    connect();

    return () => {
      controller.abort();
      if (retryTimeout) clearTimeout(retryTimeout);
    };
  }, [onUpdate]);
};
