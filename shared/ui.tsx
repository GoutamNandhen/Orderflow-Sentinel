import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ShoppingBag,
  ShieldCheck,
  Radio,
  X,
  CheckCircle2,
  TriangleAlert,
} from "lucide-react";
import { useResource } from "./api";
import type { DemoStatus } from "./types";
export const money = (paise: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(paise / 100);
export const localTime = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "medium",
      })
    : "Unavailable";
export const percent = (value: number | null | undefined) =>
  value == null ? "Unavailable" : (value * 100).toFixed(1) + "%";
export const label = (text: string) => text.replaceAll("_", " ");
export function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Priority({ value }: { value: string }) {
  return (
    <Badge tone={value === "P1" ? "red" : value === "P2" ? "amber" : "slate"}>
      {value}
      {value === "P1" ? " URGENT" : ""}
    </Badge>
  );
}
export function Card({
  children,
  title,
  action,
  className = "",
}: {
  children: ReactNode;
  title?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="card-head">
          <h3>{title}</h3>
          {action}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <CheckCircle2 size={28} />
      <p>{children}</p>
    </div>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  return error ? (
    <div role="alert" className="notice red">
      <TriangleAlert size={18} />
      <span>{error}</span>
      {retry && <button onClick={retry}>Retry</button>}
    </div>
  ) : null;
}
export function Connection({ state }: { state: string }) {
  return (
    <span className={`connection ${state === "Live" ? "online" : ""}`}>
      <Radio size={13} />
      {state === "Live" ? "Connection: Live" : state}
    </span>
  );
}
export function Switcher({
  app,
  state,
  children,
}: {
  app: "shop" | "console";
  state: string;
  children?: ReactNode;
}) {
  const demo = useResource<DemoStatus>("/api/demo/status", 3000);
  return (
    <header className="switcher">
      <div className="switcher-inner">
        <div className="switcher-left">
          <Badge tone="gold">DEMO SWITCHER</Badge>
          <a
            className={app === "shop" ? "active" : ""}
            href={
              import.meta.env.VITE_SHOP_URL ||
              (import.meta.env.DEV ? "http://localhost:5173" : "/shop/")
            }
          >
            <ShoppingBag size={13} />
            ShopEase Customer App
          </a>
          <a
            className={app === "console" ? "active" : ""}
            href={
              import.meta.env.VITE_CONSOLE_URL ||
              (import.meta.env.DEV ? "http://localhost:5174" : "/console/")
            }
          >
            <ShieldCheck size={13} />
            Sentinel Operator Console
          </a>
        </div>
        <div className="switcher-right">
          <span className="block-counter">
            5-Order Demo Block:{" "}
            <strong>Next #{demo.data?.position || "—"} of 5</strong>
            {demo.data?.forced_override_pending ? " · override pending" : ""}
          </span>
          {children}
          <Connection state={state} />
        </div>
      </div>
    </header>
  );
}
export function Elapsed({
  start,
  end,
}: {
  start: string;
  end?: string | null;
}) {
  const [time, setTime] = useState(Date.now());
  useEffect(() => {
    if (end) return;
    const id = setInterval(() => setTime(Date.now()), 1000);
    return () => clearInterval(id);
  }, [end]);
  const seconds = Math.max(
    0,
    Math.floor(
      ((end ? new Date(end).getTime() : time) - new Date(start).getTime()) /
        1000,
    ),
  );
  return (
    <span className="tabular">
      {Math.floor(seconds / 60)}m {seconds % 60}s
    </span>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    const original = document.activeElement as HTMLElement | null;
    return () => original?.focus();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-label={title}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button
          className="icon-btn"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Toast({
  text,
  onClose,
}: {
  text: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const id = setTimeout(onClose, 5000);
    return () => clearTimeout(id);
  }, [text, onClose]);
  return (
    <div className="toast" role="status">
      <CheckCircle2 size={18} />
      <span>{text}</span>
      <button aria-label="Dismiss notification" onClick={onClose}>
        <X size={16} />
      </button>
    </div>
  );
}
export function Pager({
  offset,
  total,
  onChange,
}: {
  offset: number;
  total: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + 25, total)} of ${total}`
          : "0 records"}
      </span>
      <button
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - 25))}
      >
        Previous
      </button>
      <button
        disabled={offset + 25 >= total}
        onClick={() => onChange(offset + 25)}
      >
        Next
      </button>
    </div>
  );
}
