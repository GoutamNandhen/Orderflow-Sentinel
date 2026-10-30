import { useCallback, useEffect, useRef, useState } from "react";
import type { LiveEvent } from "./types";
export const API =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : "");
export function customerSession() {
  const existing = document.cookie
    .split("; ")
    .find((s) => s.startsWith("of_customer="))
    ?.split("=")[1];
  if (existing && existing.length >= 32) return existing;
  const token = crypto.randomUUID() + crypto.randomUUID();
  document.cookie = `of_customer=${token}; Path=/; SameSite=Strict; Max-Age=31536000${location.protocol === "https:" ? "; Secure" : ""}`;
  return token;
}
export const operatorToken = () =>
  localStorage.getItem("sentinel_operator") || "";
export async function api<T>(
  path: string,
  body?: unknown,
  key?: string,
): Promise<T> {
  const response = await fetch(API + path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Customer-Session": customerSession(),
      ...(operatorToken()
        ? { Authorization: "Bearer " + operatorToken() }
        : {}),
      ...(body !== undefined
        ? { "Idempotency-Key": key || crypto.randomUUID() }
        : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "Backend unavailable" }));
    if (
      response.status === 401 &&
      path.startsWith("/api/console/") &&
      !path.endsWith("/login")
    ) {
      localStorage.removeItem("sentinel_operator");
      window.dispatchEvent(new Event("operator_expired"));
    }
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  }
  return response.json();
}
export function useResource<T>(path: string | null, interval = 0) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const sequence = useRef(0);
  const refresh = useCallback(async () => {
    if (!path) {
      setLoading(false);
      return;
    }
    const seq = ++sequence.current;
    try {
      const value = await api<T>(path);
      if (seq === sequence.current) {
        setData(value);
        setError("");
      }
    } catch (e) {
      if (seq === sequence.current) setError((e as Error).message);
    } finally {
      if (seq === sequence.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    setLoading(true);
    setData(null);
    void refresh();
    const timer = interval
      ? window.setInterval(() => void refresh(), interval)
      : undefined;
    return () => {
      sequence.current++;
      clearInterval(timer);
    };
  }, [refresh, interval]);
  return { data, error, loading, refresh };
}
export function useLive(
  path: string | null,
  onUpdate: () => void,
  onEvent?: (event: LiveEvent) => void,
) {
  const [state, setState] = useState("Connecting");
  const callback = useRef(onUpdate),
    eventCallback = useRef(onEvent);
  callback.current = onUpdate;
  eventCallback.current = onEvent;
  useEffect(() => {
    if (!path) {
      setState("No active stream");
      return;
    }
    let disposed = false,
      socket: WebSocket | undefined,
      timer: number | undefined,
      attempt = 0,
      lastId = 0;
    const versions = new Map<string, number>();
    const connect = () => {
      setState(attempt ? "Reconnecting" : "Connecting");
      const socketUrl = new URL(path, API || window.location.origin);
      socketUrl.protocol = socketUrl.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(socketUrl);
      socket.onopen = () => {
        if (disposed) return;
        attempt = 0;
        setState("Live");
      };
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as LiveEvent;
        if (event.type === "snapshot_required") {
          lastId = event.id;
          versions.clear();
          callback.current();
          return;
        }
        if (event.id <= lastId) return;
        lastId = event.id;
        const entity = event.order_id || event.type;
        if (event.entity_version < (versions.get(entity) || 0)) return;
        versions.set(entity, event.entity_version);
        callback.current();
        eventCallback.current?.(event);
      };
      socket.onerror = () => socket?.close();
      socket.onclose = (event) => {
        if (disposed) return;
        setState("Reconnecting");
        if (event.code === 4401) {
          localStorage.removeItem("sentinel_operator");
          window.dispatchEvent(new Event("operator_expired"));
          return;
        }
        timer = window.setTimeout(
          connect,
          Math.min(15000, 500 * 2 ** attempt++),
        );
      };
    };
    connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [path]);
  return state;
}
