import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ShieldCheck,
  LayoutDashboard,
  TriangleAlert,
  Package,
  History,
  Network,
  BarChart3,
  Settings2,
  Zap,
  ArrowRight,
  ExternalLink,
  Volume2,
  VolumeX,
  RefreshCw,
  Download,
  LogOut,
  CheckCircle2,
  Clock,
} from "lucide-react";
import {
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  api,
  API,
  operatorToken,
  customerSession,
  useLive,
  useResource,
} from "../../shared/api";
import type {
  Stats,
  Incident,
  Page,
  Order,
  Settings,
  Gateway,
  Job,
  Risk,
  LiveEvent,
} from "../../shared/types";
import { errors } from "../../shared/types";
import {
  Badge,
  Card,
  Empty,
  ErrorBox,
  Priority,
  Switcher,
  Toast,
  Modal,
  Elapsed,
  Connection,
  Pager,
  money,
  localTime,
  percent,
  label,
} from "../../shared/ui";

const tabs = [
  ["dashboard", "Dashboard", LayoutDashboard],
  ["incidents", "Incidents Queue", TriangleAlert],
  ["orders", "Orders", Package],
  ["history", "Resolution History", History],
  ["gateways", "Gateway Health", Network],
  ["analytics", "Analytics", BarChart3],
  ["settings", "Settings", Settings2],
] as const;
const titles: Record<string, string> = {
  dashboard: "Live Operations Dashboard",
  incidents: "Incident Queue",
  detail: "Incident Investigation",
  orders: "Platform Orders Directory",
  history: "Resolution History & Audit Log",
  gateways: "Gateway & Partner Circuit Health",
  analytics: "Incident & Recovery Analytics",
  settings: "Simulator & Guardrail Settings",
};

export default function App() {
  const [signedIn, setSignedIn] = useState(!!operatorToken()),
    [tab, setTab] = useState("dashboard"),
    [selected, setSelected] = useState(""),
    [toast, setToast] = useState(""),
    [error, setError] = useState(""),
    [simulate, setSimulate] = useState(false),
    [sound, setSound] = useState(false),
    [ack, setAck] = useState(0);
  const soundRef = useRef<AudioContext | null>(null);
  const stats = useResource<Stats>(
    signedIn ? "/api/console/stats" : null,
    10000,
  );
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const expired = () => {
      setSignedIn(false);
      setError("Operator session expired. Sign in again.");
    };
    window.addEventListener("operator_expired", expired);
    return () => window.removeEventListener("operator_expired", expired);
  }, []);
  const refresh = () => {
    void stats.refresh();
    setRevision((v) => v + 1);
  };
  const onEvent = (event: LiveEvent) => {
    if (["incident_opened", "incident_resolved"].includes(event.type))
      setToast(`${label(event.type)} · ${event.order_id}`);
    if (
      event.type === "incident_opened" &&
      event.data.priority === "P1" &&
      sound &&
      soundRef.current
    ) {
      const ctx = soundRef.current;
      const osc = ctx.createOscillator(),
        gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
    }
  };
  const connection = useLive(
    signedIn
      ? `/ws/console?token=${encodeURIComponent(operatorToken())}`
      : null,
    refresh,
    onEvent,
  );
  const inspect = (id: string) => {
    setSelected(id);
    setTab("detail");
  };
  const act = async (fn: () => Promise<unknown>, message: string) => {
    setError("");
    try {
      await fn();
      setToast(message);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await act(async () => {
      const result = await api<{ token: string }>("/api/console/login", {
        password: form.get("password"),
      });
      localStorage.setItem("sentinel_operator", result.token);
      setSignedIn(true);
    }, "Signed in to local operator console");
  }
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Switcher app="console" state={connection}>
        {signedIn && (
          <button onClick={() => setSimulate(true)}>
            <Zap size={12} />
            Simulate New Order
          </button>
        )}
      </Switcher>
      {!signedIn ? (
        <div className="login stack">
          <div className="row">
            <div className="brand-icon">
              <ShieldCheck size={24} />
            </div>
            <h1>Sentinel Operator Access</h1>
          </div>
          <Card>
            <form onSubmit={login} className="stack">
              <p className="muted">
                Sign in to investigate incidents and execute local simulated
                recovery actions.
              </p>
              <label className="field">
                Local operator password
                <input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  defaultValue=""
                />
              </label>
              <p className="tiny muted">
                Use the private operator credential configured for this
                installation. The demo switcher does not grant access.
              </p>
              <button
                className="button-primary"
                type="submit"
                style={{ width: "100%" }}
              >
                Sign In <ArrowRight size={15} />
              </button>
            </form>
          </Card>
          <ErrorBox error={error} />
        </div>
      ) : (
        <div className="console-layout">
          <aside className="sidebar">
            <div className="sidebar-brand">
              <div className="brand-icon">
                <ShieldCheck size={22} />
              </div>
              <div>
                <strong>
                  SENTINEL <em>CONSOLE</em>
                </strong>
                <p className="tiny muted">Order Incident Operations</p>
              </div>
            </div>
            <nav aria-label="Console navigation">
              {tabs.map(([id, text, Icon]) => (
                <button
                  className={
                    tab === id || (id === "incidents" && tab === "detail")
                      ? "selected"
                      : ""
                  }
                  key={id}
                  onClick={() => setTab(id)}
                >
                  <Icon size={16} />
                  <span className="grow" style={{ textAlign: "left" }}>
                    {text}
                  </span>
                  {id === "incidents" && !!stats.data?.open_incidents && (
                    <Badge tone="red">{stats.data.open_incidents}</Badge>
                  )}
                </button>
              ))}
            </nav>
            <div className="sidebar-footer tight">
              <div className="row between">
                <strong style={{ color: "white" }}>Local Demo Operator</strong>
                <Badge tone="green">On Duty</Badge>
              </div>
              <p className="muted">Simulated India operations</p>
              <button
                className="button-link"
                onClick={() => {
                  localStorage.removeItem("sentinel_operator");
                  setSignedIn(false);
                }}
              >
                <LogOut size={12} />
                Sign Out
              </button>
            </div>
          </aside>
          <div className="console-workspace">
            {stats.data && stats.data.open_p1 > ack && (
              <div className="p1-banner">
                <div className="row">
                  <Badge>P1 ALERT</Badge>
                  {stats.data.open_p1} urgent P1 incident(s) remain open.
                  Priority stays visible after recovery.
                </div>
                <div className="row">
                  <button onClick={() => setTab("incidents")}>
                    Inspect Queue
                  </button>
                  <button onClick={() => setAck(stats.data?.open_p1 || 0)}>
                    Acknowledge
                  </button>
                </div>
              </div>
            )}
            {connection !== "Live" && (
              <div className="notice" style={{ borderRadius: 0 }}>
                Telemetry {connection.toLowerCase()}. Reconnecting with backoff;
                snapshots resynchronise after reconnection.
              </div>
            )}
            <header className="workspace-head">
              <div>
                <h1>
                  {titles[tab]}
                  {tab === "detail" ? " · " + selected : ""}
                </h1>
                <p>
                  Real-time order telemetry, incident triage and risk-weighted
                  intervention · local simulation
                </p>
              </div>
              <div className="row">
                <button
                  aria-label={sound ? "Mute P1 sound" : "Enable P1 sound"}
                  onClick={() => {
                    if (!sound) {
                      soundRef.current ??= new AudioContext();
                      void soundRef.current.resume();
                    }
                    setSound((v) => !v);
                  }}
                >
                  {sound ? <Volume2 size={14} /> : <VolumeX size={14} />}P1
                  sound {sound ? "on" : "off"}
                </button>
                <Connection state={connection} />
              </div>
            </header>
            <main id="main" className="console-content stack">
              <ErrorBox
                error={error || stats.error}
                retry={() => {
                  setError("");
                  void stats.refresh();
                }}
              />
              {tab === "dashboard" &&
                (stats.loading ? (
                  <div className="loading">Loading live operations…</div>
                ) : (
                  stats.data && (
                    <Dashboard
                      data={stats.data}
                      revision={revision}
                      inspect={inspect}
                      navigate={setTab}
                    />
                  )
                ))}
              {tab === "incidents" && (
                <IncidentQueue revision={revision} inspect={inspect} />
              )}
              {tab === "detail" && (
                <IncidentDetail
                  id={selected}
                  revision={revision}
                  refresh={refresh}
                  showToast={setToast}
                  connection={connection}
                />
              )}
              {tab === "orders" && (
                <Orders
                  revision={revision}
                  inspect={inspect}
                  onError={setError}
                  refresh={refresh}
                />
              )}
              {tab === "history" && (
                <HistoryView revision={revision} inspect={inspect} />
              )}
              {tab === "gateways" && (
                <GatewayView revision={revision} act={act} />
              )}
              {tab === "analytics" && stats.data && (
                <Analytics stats={stats.data} />
              )}
              {tab === "settings" && (
                <SettingsView
                  revision={revision}
                  refresh={refresh}
                  showToast={setToast}
                  report={stats.data?.model || null}
                />
              )}
            </main>
            <footer className="footer">
              Single backend worker · SQLite · Offline service simulations · No
              external payment, SMS or paging integration
            </footer>
          </div>
        </div>
      )}
      {simulate && (
        <Simulation
          onClose={() => setSimulate(false)}
          done={(order) => {
            setToast(
              `${order.id} booked · position #${((order.booking_seq - 1) % 5) + 1}/5`,
            );
            setSimulate(false);
            refresh();
            if (order.incident_status) setTab("incidents");
          }}
        />
      )}
      {toast && <Toast text={toast} onClose={() => setToast("")} />}
    </>
  );
}

function KPI({
  title,
  value,
  note,
  urgent = false,
}: {
  title: string;
  value: string | number;
  note: string;
  urgent?: boolean;
}) {
  return (
    <div className={`kpi ${urgent ? "urgent" : ""}`}>
      <span className="kpi-label">{title}</span>
      <div className="kpi-value">{value}</div>
      <small>{note}</small>
    </div>
  );
}
function Dashboard({
  data: s,
  revision,
  inspect,
  navigate,
}: {
  data: Stats;
  revision: number;
  inspect: (id: string) => void;
  navigate: (tab: string) => void;
}) {
  const queue = useResource<Page<Incident>>(
    "/api/console/incidents?status=OPEN&limit=5",
  );
  useEffect(() => {
    void queue.refresh();
  }, [revision]);
  return (
    <>
      <div className="kpi-grid">
        <KPI
          title="Total Orders"
          value={s.total_orders}
          note="All persisted bookings"
        />
        <KPI
          title="Booking Success"
          value={percent(s.initial_success_rate)}
          note="Initial result / all bookings"
        />
        <KPI
          title="Open Incidents"
          value={s.open_incidents}
          note="Includes pending refunds"
        />
        <KPI
          title="Auto-Resolved"
          value={s.auto_resolved}
          note="Resolved by engine"
        />
        <KPI
          title="Avg Resolution"
          value={
            s.average_resolution_seconds == null
              ? "—"
              : s.average_resolution_seconds.toFixed(1) + "s"
          }
          note="Completed incidents only"
        />
        <KPI
          title="Open P1 Urgent"
          value={s.open_p1}
          note="Highest rule priority"
          urgent
        />
        <KPI
          title="Money at Risk"
          value={money(s.money_at_risk_paise)}
          note="Open captured/unknown debits"
        />
      </div>
      <Card>
        <div className="row between">
          <div>
            <h4>INITIAL BOOKING FAILURES VS. SENTINEL RECOVERED ORDERS</h4>
            <p className="tiny muted">
              Initial outcomes remain recorded after recovery. Cancellation and
              refund are excluded from recovered orders.
            </p>
          </div>
          <div className="row">
            <Badge tone="amber">Initial Failures: {s.initial_failures}</Badge>
            <Badge tone="green">
              Recovered: {s.recovered_orders} (
              {percent(s.eventual_recovery_rate)})
            </Badge>
            <Badge tone="red">Open: {s.open_incidents}</Badge>
          </div>
        </div>
      </Card>
      <div className="two-columns">
        <div className="stack">
          <Card
            title="Urgent Incident Panel · Requires Operator Action"
            className="flush"
            action={
              <button
                className="button-link"
                onClick={() => navigate("incidents")}
              >
                Open Full Queue →
              </button>
            }
          >
            {queue.data?.items.length ? (
              queue.data.items.map((i) => (
                <div className="incident-row" key={i.id}>
                  <div className="grow">
                    <div className="row">
                      <Priority value={i.priority} />
                      <strong>{i.order_id}</strong>
                      <RiskBadge risk={i.risk_breakdown} />
                      <Badge>{label(i.decision)}</Badge>
                    </div>
                    <h4>{label(i.error_type)}</h4>
                    <p>
                      {i.order.user_name} · {money(i.order.amount)} · Suggested:{" "}
                      {label(i.suggested_action)}
                    </p>
                  </div>
                  <button onClick={() => inspect(i.id)}>
                    Inspect & Resolve →
                  </button>
                </div>
              ))
            ) : (
              <Empty>
                No open incidents. Place an order to test the live workflow.
              </Empty>
            )}
          </Card>
          <Card title="Hourly Incident Detection & Recovery · Last 6 Hours">
            <Trend data={s.trend} />
          </Card>
        </div>
        <Card title="Live Order & Incident Feed">
          <div>
            {s.events.length ? (
              s.events.map((e) => (
                <div className="feed-item" key={e.id}>
                  <small>{localTime(e.timestamp)}</small>
                  <Badge
                    tone={
                      e.type === "incident_resolved"
                        ? "green"
                        : e.type === "incident_opened"
                          ? "amber"
                          : ""
                    }
                  >
                    {label(e.type)}
                  </Badge>
                  <p>
                    {e.order_id || "System"}{" "}
                    {typeof e.data.result === "string"
                      ? "· " + e.data.result
                      : ""}
                  </p>
                </div>
              ))
            ) : (
              <Empty>No events yet.</Empty>
            )}
          </div>
        </Card>
      </div>
    </>
  );
}
function Trend({ data }: { data: Stats["trend"] }) {
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data.map((d) => ({
            ...d,
            time: new Date(d.hour).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          }))}
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="time" fontSize={10} />
          <YAxis allowDecimals={false} fontSize={10} width={28} />
          <Tooltip />
          <Bar
            dataKey="detected"
            name="Detected"
            fill="#0f172a"
            radius={[3, 3, 0, 0]}
          />
          <Bar
            dataKey="recovered"
            name="Recovered"
            fill="#10b981"
            radius={[3, 3, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
function RiskBadge({ risk }: { risk: Risk }) {
  return (
    <Badge
      tone={
        risk.tier === "HIGH" ? "red" : risk.tier === "MED" ? "amber" : "green"
      }
    >
      {risk.score.toFixed(2)}/100 {risk.tier}
    </Badge>
  );
}

function IncidentQueue({
  revision,
  inspect,
}: {
  revision: number;
  inspect: (id: string) => void;
}) {
  const [filters, setFilters] = useState({
      q: "",
      priority: "",
      risk: "",
      decision: "",
      status: "OPEN",
      error_type: "",
    }),
    [offset, setOffset] = useState(0);
  const query = new URLSearchParams({
    ...filters,
    offset: String(offset),
    limit: "25",
  }).toString();
  const resource = useResource<Page<Incident>>(
    "/api/console/incidents?" + query,
  );
  useEffect(() => {
    void resource.refresh();
  }, [revision]);
  const update = (key: string, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setOffset(0);
  };
  return (
    <>
      <Card>
        <div className="filter-bar">
          <input
            aria-label="Search incidents"
            placeholder="Search order, customer or problem…"
            value={filters.q}
            onChange={(e) => update("q", e.target.value)}
          />
          <select
            aria-label="Priority filter"
            value={filters.priority}
            onChange={(e) => update("priority", e.target.value)}
          >
            <option value="">Priority: All</option>
            {["P1", "P2", "P3"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
          <select
            aria-label="Risk filter"
            value={filters.risk}
            onChange={(e) => update("risk", e.target.value)}
          >
            <option value="">Risk: All</option>
            {["LOW", "MED", "HIGH"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
          <select
            aria-label="Handling filter"
            value={filters.decision}
            onChange={(e) => update("decision", e.target.value)}
          >
            <option value="">Handling: All</option>
            {["AUTO", "ONE_CLICK", "MANUAL"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
          <select
            aria-label="Incident status filter"
            value={filters.status}
            onChange={(e) => update("status", e.target.value)}
          >
            <option value="">Status: All</option>
            <option value="OPEN">Open / Pending</option>
            <option value="RESOLVED">Resolved</option>
            <option value="ESCALATED">Escalated</option>
          </select>
          <select
            aria-label="Error type filter"
            value={filters.error_type}
            onChange={(e) => update("error_type", e.target.value)}
          >
            <option value="">Error: All 10 types</option>
            {errors.map((p) => (
              <option key={p} value={p}>
                {label(p)}
              </option>
            ))}
          </select>
          <button
            onClick={() => {
              setFilters({
                q: "",
                priority: "",
                risk: "",
                decision: "",
                status: "",
                error_type: "",
              });
              setOffset(0);
            }}
          >
            Reset
          </button>
        </div>
        <p className="tiny muted" style={{ marginTop: 12 }}>
          Sorted by P1 urgency first, then descending unrounded action risk. LOW
          ≤30 · MED &gt;30–60 · HIGH &gt;60.
        </p>
      </Card>
      <ErrorBox error={resource.error} retry={() => void resource.refresh()} />
      <IncidentTable
        resource={resource}
        inspect={inspect}
        offset={offset}
        setOffset={setOffset}
      />
    </>
  );
}
function IncidentTable({
  resource,
  inspect,
  offset,
  setOffset,
}: {
  resource: ReturnType<typeof useResource<Page<Incident>>>;
  inspect: (id: string) => void;
  offset: number;
  setOffset: (n: number) => void;
}) {
  return (
    <section className="card">
      {resource.loading ? (
        <div className="loading">Loading incidents…</div>
      ) : resource.data?.items.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "Order ID",
                  "Problem & Customer",
                  "Priority",
                  "Action Risk",
                  "Confidence",
                  "Handling",
                  "Status",
                  "Time Open",
                  "Action",
                ].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {resource.data.items.map((i) => (
                <tr key={i.id}>
                  <td>
                    <strong>{i.order_id}</strong>
                    {i.order.simulator_override && (
                      <p className="tiny muted">Explicit override</p>
                    )}
                  </td>
                  <td className="problem">
                    <strong>{label(i.error_type)}</strong>
                    <p className="muted">
                      {i.order.user_name} · {money(i.order.amount)}
                    </p>
                  </td>
                  <td>
                    <Priority value={i.priority} />
                  </td>
                  <td>
                    <RiskBadge risk={i.risk_breakdown} />
                  </td>
                  <td>
                    {percent(i.model_output.confidence)}
                    <p className="tiny muted">
                      {i.model_output.version ? "Model" : "Rule fallback"}
                    </p>
                  </td>
                  <td>
                    <Badge>{label(i.decision)}</Badge>
                  </td>
                  <td>
                    <Badge tone={i.status === "RESOLVED" ? "green" : "amber"}>
                      {label(i.status)}
                    </Badge>
                  </td>
                  <td>
                    <Elapsed start={i.detected_at} end={i.resolved_at} />
                  </td>
                  <td>
                    <button onClick={() => inspect(i.id)}>Inspect</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>No incidents match your filters.</Empty>
      )}
      <Pager
        offset={offset}
        total={resource.data?.total || 0}
        onChange={setOffset}
      />
    </section>
  );
}

function IncidentDetail({
  id,
  revision,
  refresh,
  showToast,
  connection,
}: {
  id: string;
  revision: number;
  refresh: () => void;
  showToast: (s: string) => void;
  connection: string;
}) {
  const resource = useResource<Incident>(
      id ? `/api/console/incidents/${id}` : null,
    ),
    [selected, setSelected] = useState(""),
    [note, setNote] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [confirm, setConfirm] = useState(false);
  useEffect(() => {
    void resource.refresh();
  }, [revision]);
  useEffect(() => {
    setSelected("");
    setNote("");
    setError("");
  }, [id]);
  const inc = resource.data,
    action = selected || inc?.suggested_action || "",
    score = inc?.action_scores?.[action];
  async function submit(
    endpoint: "action" | "approve" | "reject",
    confirmed = false,
  ) {
    if (!inc) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ ok: boolean; message: string }>(
        `/api/console/incidents/${id}/${endpoint}`,
        { action, expected_version: inc.version, note, confirmed },
      );
      if (!result.ok) setError(result.message);
      else {
        showToast(result.message);
        setNote("");
      }
      setConfirm(false);
      void resource.refresh();
      refresh();
    } catch (e) {
      setError((e as Error).message);
      void resource.refresh();
    } finally {
      setBusy(false);
    }
  }
  async function logNote() {
    if (!inc || !note.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/console/incidents/${id}/notes`, {
        note,
        expected_version: inc.version,
      });
      setNote("");
      showToast("Operator note recorded");
      void resource.refresh();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (resource.loading)
    return <div className="loading">Loading investigation…</div>;
  if (!inc)
    return (
      <ErrorBox
        error={resource.error || "Choose an incident from the queue."}
      />
    );
  const risk = score?.risk || inc.risk_breakdown,
    disabled = busy || connection !== "Live" || inc.status === "RESOLVED";
  return (
    <>
      <ErrorBox error={error || resource.error} />
      <div className="two-columns">
        <div className="stack">
          <Card>
            <div className="row between">
              <div className="row">
                <h2>{inc.order_id}</h2>
                <Priority value={inc.priority} />
                <RiskBadge risk={risk} />
                <Badge tone={inc.status === "RESOLVED" ? "green" : "amber"}>
                  {label(inc.status)}
                </Badge>
              </div>
              <div className="text-right">
                <small className="muted">Actual elapsed time</small>
                <div style={{ fontSize: 21, fontWeight: 700 }}>
                  <Elapsed start={inc.detected_at} end={inc.resolved_at} />
                </div>
              </div>
            </div>
            <p className="tiny muted" style={{ marginTop: 10 }}>
              {inc.order.user_name} · {inc.order.phone} ·{" "}
              {money(inc.order.amount)} · Payment:{" "}
              {label(inc.order.payment.status)}
            </p>
            <div className="notice slate" style={{ marginTop: 18 }}>
              <ShieldCheck size={18} />
              <div>
                <h4>WHAT HAPPENED · PLAIN ENGLISH</h4>
                {inc.explanation.operator.map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            </div>
            <dl className="order-grid" style={{ marginTop: 18 }}>
              <div>
                <dt>Why {inc.priority} was assigned</dt>
                <dd>{inc.explanation.priority_reasons.join(" · ")}</dd>
              </div>
              <div>
                <dt>Promised delivery</dt>
                <dd>{localTime(inc.order.promised_by)}</dd>
              </div>
              <div>
                <dt>Estimated delivery delay</dt>
                <dd>
                  +{inc.forecast.delay_minutes.toFixed(1)} minutes · estimate
                </dd>
              </div>
              <div>
                <dt>Estimated incident repair time</dt>
                <dd>
                  {inc.forecast.repair_seconds == null
                    ? "Unavailable"
                    : inc.forecast.repair_seconds + "s"}
                </dd>
              </div>
            </dl>
            <p className="tiny muted" style={{ marginTop: 12 }}>
              {inc.forecast.source} · {inc.forecast.sample_count}{" "}
              completed-delivery samples
            </p>
            {inc.order.simulator_override && (
              <p className="notice" style={{ marginTop: 12 }}>
                Explicit simulator override · profile {inc.order.profile}. This
                may break the default three-failures-per-five pattern. Model
                inference remains real.
              </p>
            )}
          </Card>
          <Card title="Operator Resolution Controls">
            <div className="suggested tight">
              <div className="row between">
                <Badge tone="amber">SENTINEL RECOMMENDATION</Badge>
                <Badge>{label(inc.decision)}</Badge>
              </div>
              <h3>{label(inc.suggested_action)}</h3>
              <p className="tiny">{inc.explanation.customer}</p>
              <p className="tiny muted">
                Selected action: {label(action)} · Recalculated policy:{" "}
                {label(score?.decision || inc.decision)}
              </p>
            </div>
            <div className="action-grid" style={{ margin: "18px 0" }}>
              {Object.entries(inc.actions || {}).map(([name, status]) => (
                <div
                  key={name}
                  className={`action-option ${action === name ? "selected" : ""}`}
                >
                  <button
                    disabled={!status.enabled || disabled}
                    onClick={() => setSelected(name)}
                  >
                    {label(name)}
                  </button>
                  {status.reason && <small>{status.reason}</small>}
                </div>
              ))}
            </div>
            <label className="field">
              Operator audit note
              <textarea
                value={note}
                maxLength={1000}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Record evidence checked and reason for action…"
              />
            </label>
            <div className="row" style={{ marginTop: 14 }}>
              <button
                disabled={busy || connection !== "Live" || !note.trim()}
                onClick={() => void logNote()}
              >
                Log Note
              </button>
              <button
                className={
                  ["REFUND", "CANCEL"].includes(action)
                    ? "button-danger"
                    : "button-primary"
                }
                disabled={disabled || !inc.actions?.[action]?.enabled}
                onClick={() =>
                  ["REFUND", "CANCEL"].includes(action)
                    ? setConfirm(true)
                    : void submit("action")
                }
              >
                {busy ? "Working…" : `Execute ${label(action)}`}
              </button>
              <button
                className="button-gold"
                disabled={
                  disabled ||
                  inc.decision === "MANUAL" ||
                  action !== inc.suggested_action ||
                  !inc.actions?.[action]?.enabled ||
                  ["REFUND", "CANCEL"].includes(action)
                }
                title={
                  inc.decision === "MANUAL"
                    ? "Manual incidents require explicit reviewed action"
                    : "Approve suggested action"
                }
                onClick={() => void submit("approve")}
              >
                Approve Suggested
              </button>
              <button disabled={disabled} onClick={() => void submit("reject")}>
                Reject Suggestion
              </button>
            </div>
            <p className="tiny muted" style={{ marginTop: 12 }}>
              Notifications, escalation, payment reconciliation and pending
              offers do not resolve the underlying fault. Explicit execution is
              the reviewed manual path.
            </p>
            {inc.order.pending_offer && (
              <p className="notice" style={{ marginTop: 14 }}>
                Waiting for customer acceptance:{" "}
                {inc.order.pending_offer.message}
              </p>
            )}
          </Card>
          <Card title="Persistent Recovery Jobs">
            {inc.jobs?.length ? (
              inc.jobs.map((j) => (
                <div className="summary-line" key={j.id}>
                  <div>
                    <strong>{j.kind}</strong>
                    <p className="tiny muted">{localTime(j.due_at)}</p>
                  </div>
                  <Badge
                    tone={
                      j.status === "PENDING"
                        ? "amber"
                        : j.status === "DONE"
                          ? "green"
                          : ""
                    }
                  >
                    {j.status}
                  </Badge>
                </div>
              ))
            ) : (
              <p className="muted tiny">No scheduled jobs for this incident.</p>
            )}
          </Card>
        </div>
        <div className="stack">
          <RiskBreakdown risk={risk} priority={inc.priority} />
          <Card title="Model Outputs & Detection">
            <div className="tight tiny">
              <Badge>
                {inc.model_output.version ? "MODEL INFERENCE" : "RULE FALLBACK"}
              </Badge>
              <p>{inc.model_output.source}</p>
              <div className="summary-line">
                <span>Error class</span>
                <strong>{inc.model_output.error_class}</strong>
              </div>
              <div className="summary-line">
                <span>Maximum class probability</span>
                <strong>{percent(inc.model_output.confidence)}</strong>
              </div>
              <div className="summary-line">
                <span>Unresolved in 5 minutes</span>
                <strong>{percent(inc.model_output.failure_probability)}</strong>
              </div>
              <div className="summary-line">
                <span>Raw anomaly decision_function</span>
                <strong>
                  {inc.model_output.anomaly_raw?.toFixed(6) ?? "Unavailable"}
                </strong>
              </div>
              <p className="muted">
                Negative raw output indicates an anomaly. Display normalisation:
                clip(0.5 − raw, 0, 1). Class probability is not proof of action
                safety.
              </p>
              <details>
                <summary>Version & prediction features</summary>
                <pre>
                  {JSON.stringify(
                    {
                      version: inc.model_output.version,
                      features: inc.model_output.features,
                      signals: inc.explanation.signals,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <details>
                <summary>Retrieved playbook · exact JSON lookup</summary>
                <pre>{JSON.stringify(inc.playbook, null, 2)}</pre>
              </details>
              <p className="muted">Explanation: {inc.explanation.source}</p>
            </div>
          </Card>
          <Card title="Chronological Audit Timeline">
            {inc.audit?.map((a) => (
              <div className="audit-item" key={a.id}>
                <small>
                  {localTime(a.timestamp)} · {a.done_by}
                </small>
                <strong>
                  {label(a.action)}
                  {a.attempt_no ? ` · attempt ${a.attempt_no}` : ""}
                </strong>
                <p>{a.result}</p>
                {a.note && (
                  <p>
                    <em>Note: {a.note}</em>
                  </p>
                )}
                <Badge>
                  {a.before_status} → {a.after_status}
                </Badge>
              </div>
            ))}
          </Card>
          {!!inc.feedback?.length && (
            <Card title="Operator Feedback · Preferences">
              <div className="tight">
                {inc.feedback.map((f, i) => (
                  <p className="tiny" key={i}>
                    <Badge>{f.operator_decision}</Badge>{" "}
                    {label(f.chosen_action)}
                    <br />
                    {f.comment || "No note"}
                    <br />
                    <small className="muted">
                      {localTime(f.timestamp)} · not a verified outcome label
                    </small>
                  </p>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
      {confirm && (
        <Modal
          title={`Confirm ${label(action)} · ${inc.order_id}`}
          onClose={() => setConfirm(false)}
        >
          <div className="stack">
            <p>
              You are about to{" "}
              {action === "REFUND"
                ? `request a simulated refund of ${money(inc.order.amount)}`
                : "cancel this uncharged order"}
              . This action requires explicit operator confirmation.
            </p>
            <div className="notice red">
              <TriangleAlert size={18} />
              Refund settlement is asynchronous; a request remains pending until
              the local simulated settlement confirms it. No real money moves.
            </div>
            <p>
              Selected-action risk: {risk.score.toFixed(4)} / 100 ·{" "}
              {score?.decision}
            </p>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button onClick={() => setConfirm(false)}>Go Back</button>
              <button
                className="button-danger"
                disabled={busy}
                onClick={() => void submit("action", true)}
              >
                Confirm & Execute
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
function RiskBreakdown({
  risk: r,
  priority,
}: {
  risk: Risk;
  priority: string;
}) {
  return (
    <Card title="Risk Score Breakdown">
      <div className="row between">
        <div>
          <div className="risk-total">
            {r.score.toFixed(2)}
            <span className="muted" style={{ fontSize: 14 }}>
              {" "}
              / 100
            </span>
          </div>
          <small className="muted">Action: {label(r.action)}</small>
        </div>
        <RiskBadge risk={r} />
      </div>
      <div className="notice slate" style={{ marginTop: 14 }}>
        Priority ({priority}) measures urgency. Risk measures the consequence
        and uncertainty of this specific action.
      </div>
      {Object.entries(r.components).map(([name, value]) => (
        <div className="risk-line" key={name}>
          <div className="row between">
            <span>
              {label(name)} · {r.weights[name] * 100}%
            </span>
            <strong>
              {value.toFixed(3)} × {r.weights[name]} ={" "}
              {r.contributions[name].toFixed(3)}
            </strong>
          </div>
          <div className="progress">
            <span
              style={{
                width: value + "%",
                background:
                  name === "uncertainty"
                    ? "#f59e0b"
                    : name === "no_undo"
                      ? "#ef4444"
                      : "#0f172a",
              }}
            />
          </div>
        </div>
      ))}
      <p className="tiny muted" style={{ marginTop: 16 }}>
        Charged-customer impact bump: {r.charged_bump}, capped at 100. Sum of
        contributions ={" "}
        {Object.values(r.contributions)
          .reduce((a, b) => a + b, 0)
          .toFixed(6)}
        . Decisions use unrounded values.
      </p>
    </Card>
  );
}

function Orders({
  revision,
  inspect,
  onError,
  refresh,
}: {
  revision: number;
  inspect: (id: string) => void;
  onError: (s: string) => void;
  refresh: () => void;
}) {
  const [q, setQ] = useState(""),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState("");
  const resource = useResource<Page<Order>>(
    `/api/console/orders?q=${encodeURIComponent(q)}&offset=${offset}`,
  );
  useEffect(() => {
    void resource.refresh();
  }, [revision]);
  async function advance(o: Order) {
    setBusy(o.id);
    try {
      const states = ["UNFULFILLED", "PACKED", "OUT_FOR_DELIVERY", "DELIVERED"];
      await api(`/api/console/orders/${o.id}/fulfilment`, {
        state: states[states.indexOf(o.fulfilment) + 1],
        expected_version: o.version,
      });
      refresh();
      void resource.refresh();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <Card>
        <input
          aria-label="Search orders"
          placeholder="Search order ID or customer…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
        />
      </Card>
      <ErrorBox error={resource.error} />
      <section className="card">
        {resource.loading ? (
          <div className="loading">Loading orders…</div>
        ) : resource.data?.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Order ID",
                    "Customer & Items",
                    "Amount",
                    "Payment / Refund",
                    "Order / Delivery",
                    "Incident",
                    "Actions",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resource.data.items.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <strong>{o.id}</strong>
                      <p className="muted">
                        Position #{((o.booking_seq - 1) % 5) + 1}/5
                      </p>
                      <Badge tone={o.initial_failed ? "amber" : "green"}>
                        Initial {o.initial_failed ? "failure" : "success"}
                      </Badge>
                    </td>
                    <td className="problem">
                      <strong>{o.user_name}</strong>
                      <p className="muted">
                        {o.pincode} ·{" "}
                        {o.items.map((i) => `${i.qty}× ${i.name}`).join(", ")}
                      </p>
                    </td>
                    <td>
                      {money(o.amount)}
                      <p>
                        <Priority value={o.priority} />
                      </p>
                    </td>
                    <td>
                      {label(o.payment.status)}
                      {o.refund && <p>Refund: {o.refund.status}</p>}
                    </td>
                    <td>
                      <Badge>{label(o.status)}</Badge>
                      <p>{label(o.fulfilment)}</p>
                    </td>
                    <td>{o.incident_status || "No incident"}</td>
                    <td>
                      <div className="tight">
                        {o.incident_id && (
                          <button onClick={() => inspect(o.incident_id!)}>
                            Investigate
                          </button>
                        )}
                        {o.fulfilment !== "DELIVERED" && (
                          <button
                            disabled={
                              !["CONFIRMED", "RESOLVED"].includes(o.status) ||
                              busy === o.id
                            }
                            onClick={() => void advance(o)}
                          >
                            Simulate next delivery step
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No orders yet.</Empty>
        )}
        <Pager
          offset={offset}
          total={resource.data?.total || 0}
          onChange={setOffset}
        />
      </section>
    </>
  );
}

function HistoryView({
  revision,
  inspect,
}: {
  revision: number;
  inspect: (s: string) => void;
}) {
  const [filters, setFilters] = useState({
      q: "",
      risk: "",
      actor: "",
      since: "",
      until: "",
    }),
    [offset, setOffset] = useState(0),
    [error, setError] = useState("");
  const query = new URLSearchParams({
      ...filters,
      offset: String(offset),
    }).toString(),
    resource = useResource<Page<Incident>>("/api/console/history?" + query);
  useEffect(() => {
    void resource.refresh();
  }, [revision]);
  const update = (key: string, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setOffset(0);
  };
  async function download() {
    try {
      const response = await fetch(
        API + "/api/console/history?" + query + "&format=csv",
        {
          headers: {
            Authorization: "Bearer " + operatorToken(),
            "X-Customer-Session": customerSession(),
          },
        },
      );
      if (!response.ok) throw new Error("CSV export failed");
      const url = URL.createObjectURL(await response.blob()),
        a = document.createElement("a");
      a.href = url;
      a.download = "sentinel-filtered-history.csv";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <Card>
        <div className="filter-bar">
          <input
            aria-label="Search resolution history"
            placeholder="Search order, customer or error…"
            value={filters.q}
            onChange={(e) => update("q", e.target.value)}
          />
          <select
            aria-label="History risk filter"
            value={filters.risk}
            onChange={(e) => update("risk", e.target.value)}
          >
            <option value="">Risk: All</option>
            {["LOW", "MED", "HIGH"].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <select
            aria-label="History actor filter"
            value={filters.actor}
            onChange={(e) => update("actor", e.target.value)}
          >
            <option value="">Actor: All</option>
            <option value="ENGINE">Engine</option>
            <option value="OPERATOR">Operator</option>
            <option value="CUSTOMER_ACCEPTANCE">Customer acceptance</option>
            <option value="SIMULATED_SETTLEMENT">Simulated settlement</option>
          </select>
          <label className="tiny">
            Since (local)
            <input
              aria-label="History since"
              type="datetime-local"
              onChange={(e) =>
                update(
                  "since",
                  e.target.value ? new Date(e.target.value).toISOString() : "",
                )
              }
            />
          </label>
          <label className="tiny">
            Until (local)
            <input
              aria-label="History until"
              type="datetime-local"
              onChange={(e) =>
                update(
                  "until",
                  e.target.value ? new Date(e.target.value).toISOString() : "",
                )
              }
            />
          </label>
          <button onClick={() => void download()}>
            <Download size={14} />
            Export Filtered CSV
          </button>
        </div>
        <p className="tiny muted" style={{ marginTop: 12 }}>
          CSV applies these same server-side filters across all matching rows,
          up to 10,000 records. Open incidents are excluded.
        </p>
      </Card>
      <ErrorBox error={resource.error || error} />
      <section className="card">
        {resource.loading ? (
          <div className="loading">Loading resolution history…</div>
        ) : resource.data?.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Order ID",
                    "Error Detected",
                    "Resolution Action",
                    "Actor",
                    "Priority / Risk",
                    "Detected",
                    "Resolved",
                    "Actual Duration",
                    "Inspect",
                  ].map((title) => (
                    <th key={title}>{title}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resource.data.items.map((inc) => (
                  <tr key={inc.id}>
                    <td>
                      <strong>{inc.order_id}</strong>
                    </td>
                    <td>{label(inc.error_type)}</td>
                    <td>{label(inc.risk_breakdown.action)}</td>
                    <td>
                      <Badge>{label(inc.resolved_by || "Unavailable")}</Badge>
                    </td>
                    <td>
                      <Priority value={inc.priority} />
                      <p style={{ marginTop: 6 }}>
                        <RiskBadge risk={inc.risk_breakdown} />
                      </p>
                    </td>
                    <td>{localTime(inc.detected_at)}</td>
                    <td>{localTime(inc.resolved_at)}</td>
                    <td>{inc.time_to_fix_sec?.toFixed(2)}s</td>
                    <td>
                      <button onClick={() => inspect(inc.id)}>Inspect</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No resolved incidents match these filters.</Empty>
        )}
        <Pager
          offset={offset}
          total={resource.data?.total || 0}
          onChange={setOffset}
        />
      </section>
    </>
  );
}

function GatewayView({
  revision,
  act,
}: {
  revision: number;
  act: (fn: () => Promise<unknown>, s: string) => Promise<void>;
}) {
  const resource = useResource<Gateway[]>("/api/console/gateways", 5000);
  useEffect(() => {
    void resource.refresh();
  }, [revision]);
  return (
    <>
      <div className="notice slate">
        <Network size={18} />
        Local simulated gateways · five failures in a rolling minute opens a
        circuit. After 30 seconds a single half-open probe is permitted. Unknown
        debits must be reconciled before any gateway switch.
      </div>
      <ErrorBox error={resource.error} />
      <div className="three-columns">
        {resource.data?.map((g) => (
          <Card title={g.gateway_name} key={g.gateway_name}>
            <div className="tight">
              <Badge
                tone={
                  g.circuit_state === "CLOSED"
                    ? "green"
                    : g.circuit_state === "OPEN"
                      ? "red"
                      : "amber"
                }
              >
                {label(g.circuit_state)}
              </Badge>
              <div className="gateway-state">
                {g.last_errors_1min}
                <small className="muted" style={{ fontSize: 11 }}>
                  {" "}
                  errors / rolling minute
                </small>
              </div>
              <p className="tiny muted">
                {g.circuit_state === "CLOSED"
                  ? "Healthy: simulated requests may proceed."
                  : g.circuit_state === "OPEN"
                    ? "Paused: no requests until cooldown expires."
                    : "Testing recovery: only one controlled probe is permitted."}
              </p>
              <p className="tiny muted">
                Latency & success rate: unavailable · no real provider telemetry
              </p>
              <p className="tiny muted">Updated {localTime(g.updated_at)}</p>
              {g.opened_at && g.circuit_state === "OPEN" && (
                <p className="tiny">
                  Opened {localTime(g.opened_at)} · 30 second cooldown
                </p>
              )}
              <div className="row">
                <button
                  disabled={g.circuit_state !== "HALF_OPEN" || g.probe_claimed}
                  onClick={() =>
                    void act(async () => {
                      await api(
                        `/api/console/gateways/${encodeURIComponent(g.gateway_name)}/probe`,
                        { success: true },
                      );
                      void resource.refresh();
                    }, "Successful local probe recorded")
                  }
                >
                  Demo probe: success
                </button>
                <button
                  disabled={g.circuit_state !== "HALF_OPEN" || g.probe_claimed}
                  onClick={() =>
                    void act(async () => {
                      await api(
                        `/api/console/gateways/${encodeURIComponent(g.gateway_name)}/probe`,
                        { success: false },
                      );
                      void resource.refresh();
                    }, "Failed local probe recorded")
                  }
                >
                  Demo probe: fail
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}

function Analytics({ stats: s }: { stats: Stats }) {
  const colors = ["#0f172a", "#f59e0b", "#10b981"];
  return (
    <>
      <div className="equal-columns">
        <Card title="Errors by Type · All Recorded Incidents">
          {s.errors_by_type.length ? (
            <div className="chart" style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={s.errors_by_type}
                  layout="vertical"
                  margin={{ left: 55 }}
                >
                  <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                  <XAxis type="number" allowDecimals={false} fontSize={10} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={100}
                    fontSize={9}
                  />
                  <Tooltip />
                  <Bar dataKey="count" fill="#0f172a" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty>No incidents to analyse.</Empty>
          )}
        </Card>
        <Card title="Handling Mode Split · Current Decisions">
          {s.handling.some((h) => h.count) ? (
            <div className="chart">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={s.handling}
                    dataKey="count"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={75}
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {s.handling.map((h, i) => (
                      <Cell key={h.name} fill={colors[i]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty>No handling decisions yet.</Empty>
          )}
          <p className="tiny muted">
            Decisions can change after operator review, deadline monitoring or
            retry exhaustion.
          </p>
        </Card>
        <Card title="Average Completed Resolution Time · Seconds">
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={s.trend.map((d) => ({
                  ...d,
                  time: new Date(d.hour).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  }),
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" fontSize={10} />
                <YAxis fontSize={10} width={35} />
                <Tooltip />
                <Line
                  dataKey="mean_seconds"
                  name="Mean seconds"
                  stroke="#d97706"
                  strokeWidth={2}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="tiny muted">
            Unavailable hourly means remain gaps. Overall:{" "}
            {s.average_resolution_seconds == null
              ? "Unavailable"
              : s.average_resolution_seconds.toFixed(2) + "s"}
            .
          </p>
        </Card>
        <Card title="Action Risk Distribution">
          <div className="three-columns">
            {s.risk_distribution.map((d, i) => (
              <div
                className={`notice ${i === 2 ? "red" : i === 0 ? "green" : ""}`}
                key={d.name}
                style={{ display: "block" }}
              >
                <h4>{d.name}</h4>
                <div className="risk-total">{d.count}</div>
                <p className="tiny">
                  {i === 0 ? "≤30" : i === 1 ? ">30 and ≤60" : ">60"}
                </p>
              </div>
            ))}
          </div>
          <p className="tiny muted" style={{ marginTop: 16 }}>
            Current action-specific scores. All data comes from the local
            database; no sample business statistics.
          </p>
        </Card>
      </div>
      <Card title="Measured Synthetic Model Evaluation">
        {s.model ? (
          <div className="tight">
            <p>
              <Badge>{s.model.version}</Badge> ·{" "}
              {s.model.dataset_size.toLocaleString()} synthetic examples
            </p>
            <p className="tiny">
              Split: {JSON.stringify(s.model.splits)} · seed {s.model.seed}
            </p>
            <div className="equal-columns">
              <div>
                <h4>Failure Model</h4>
                {Object.entries(s.model.failure_metrics).map(([k, v]) => (
                  <div key={k} className="summary-line">
                    <span>{label(k)}</span>
                    <strong>{v.toFixed(6)}</strong>
                  </div>
                ))}
              </div>
              <div>
                <h4>Error Classifier</h4>
                {Object.entries(s.model.class_metrics)
                  .filter(([k]) => k !== "confusion_matrix")
                  .map(([k, v]) => (
                    <div key={k} className="summary-line">
                      <span>{label(k)}</span>
                      <strong>
                        {typeof v === "number" ? v.toFixed(6) : "See report"}
                      </strong>
                    </div>
                  ))}
              </div>
            </div>
            <p className="tiny muted">{s.model.feedback_note}</p>
            {s.model.limitations.map((l) => (
              <p className="tiny muted" key={l}>
                • {l}
              </p>
            ))}
          </div>
        ) : (
          <Empty>
            No trained model. Rules are active and probabilities are
            unavailable.
          </Empty>
        )}
      </Card>
    </>
  );
}

function SettingsView({
  revision,
  refresh,
  showToast,
  report,
}: {
  revision: number;
  refresh: () => void;
  showToast: (s: string) => void;
  report: Stats["model"];
}) {
  const resource = useResource<Settings>("/api/console/settings"),
    jobs = useResource<Job[]>("/api/console/jobs", 2000);
  const [draft, setDraft] = useState<Settings | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (resource.data) setDraft(resource.data);
  }, [resource.data]);
  const training = jobs.data?.find((j) => j.kind === "TRAIN");
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/console/settings", draft);
      showToast("Simulator and guardrail settings saved");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function retrain() {
    setBusy(true);
    setError("");
    try {
      await api("/api/console/retrain", {});
      showToast("Actual background training job started");
      void jobs.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  return (
    <div className="stack" style={{ maxWidth: 950 }}>
      <ErrorBox error={error || resource.error || jobs.error} />
      {draft && (
        <form onSubmit={save} className="stack">
          <Card title="Hackathon Demo Error Simulator">
            <div className="stack">
              <div className="row between">
                <p className="tiny muted">
                  All checkout paths use the same atomic persistent booking
                  sequence.
                </p>
                <label className="row">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(e) => update("enabled", e.target.checked)}
                  />
                  Simulator Active
                </label>
              </div>
              <h4>
                5-Booking Block Failure Pattern · Default positions 2, 4 and 5
              </h4>
              <div className="pattern">
                {[1, 2, 3, 4, 5].map((pos) => (
                  <button
                    type="button"
                    aria-pressed={draft.failing_positions.includes(pos)}
                    className={
                      draft.failing_positions.includes(pos) ? "fails" : ""
                    }
                    key={pos}
                    onClick={() =>
                      update(
                        "failing_positions",
                        draft.failing_positions.includes(pos)
                          ? draft.failing_positions.filter((p) => p !== pos)
                          : [...draft.failing_positions, pos].sort(),
                      )
                    }
                  >
                    <strong>{pos}</strong>
                    <small>
                      {draft.failing_positions.includes(pos)
                        ? "Fails Initially"
                        : "Succeeds"}
                    </small>
                  </button>
                ))}
              </div>
              <div className="form-grid">
                <label>
                  Error selection
                  <select
                    value={draft.selection}
                    onChange={(e) =>
                      update(
                        "selection",
                        e.target.value as Settings["selection"],
                      )
                    }
                  >
                    <option value="rotation">
                      Rotate across all ten errors
                    </option>
                    <option value="weighted">Seeded weighted selection</option>
                  </select>
                </label>
                <label>
                  Seed
                  <input
                    type="number"
                    min={0}
                    max={2147483647}
                    value={draft.seed}
                    onChange={(e) => update("seed", Number(e.target.value))}
                  />
                </label>
                <label className="span-all">
                  Force Specific Error Once · explicit override
                  <select
                    value={draft.force_error || ""}
                    onChange={(e) =>
                      update("force_error", e.target.value || null)
                    }
                  >
                    <option value="">Follow configured pattern</option>
                    {errors.map((e) => (
                      <option key={e} value={e}>
                        {label(e)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="notice tiny">
                A forced error applies to the next valid booking, including a
                normally healthy position or a disabled simulator. It is
                consumed once in the booking transaction and labelled in
                history. Validation failures and duplicate requests do not
                consume it.
              </p>
              <label className="field">
                Simulated retry failures before success (0–3)
                <input
                  type="number"
                  min={0}
                  max={3}
                  value={draft.retry_failures}
                  onChange={(e) =>
                    update("retry_failures", Number(e.target.value))
                  }
                />
              </label>
            </div>
          </Card>
          <Card title="Autonomous Guardrails & Deadline Alerts">
            <div className="form-grid">
              <label>
                Minimum Auto Confidence · {percent(draft.auto_confidence)}
                <input
                  type="range"
                  min="0.9"
                  max="1"
                  step="0.01"
                  value={draft.auto_confidence}
                  onChange={(e) =>
                    update("auto_confidence", Number(e.target.value))
                  }
                />
              </label>
              <label>
                Maximum Auto Risk · {draft.auto_risk}/100
                <input
                  type="range"
                  min="0"
                  max="30"
                  step="1"
                  value={draft.auto_risk}
                  onChange={(e) => update("auto_risk", Number(e.target.value))}
                />
              </label>
              <label>
                P2 High Value Threshold · paise
                <input
                  type="number"
                  min={10000}
                  max={100000000}
                  value={draft.high_value_paise}
                  onChange={(e) =>
                    update("high_value_paise", Number(e.target.value))
                  }
                />
              </label>
              <label>
                Close Deadline Window · minutes
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={draft.close_deadline_minutes}
                  onChange={(e) =>
                    update("close_deadline_minutes", Number(e.target.value))
                  }
                />
              </label>
              <label>
                Deadline Alert Fraction
                <input
                  type="number"
                  min={0.1}
                  max={0.95}
                  step={0.05}
                  value={draft.alert_fraction}
                  onChange={(e) =>
                    update("alert_fraction", Number(e.target.value))
                  }
                />
              </label>
            </div>
            <p className="tiny muted" style={{ marginTop: 16 }}>
              Default 0.70 alerts at minute 28 of a 40-minute promise. Monitor
              checks every 0.4 seconds. Confidence &lt;0.70 or risk &gt;60
              always requires manual handling. Settings can make auto handling
              stricter, and explicit action restrictions still apply.
            </p>
            <button
              style={{ marginTop: 18 }}
              className="button-primary"
              type="submit"
              disabled={busy}
            >
              Save Persistent Settings
            </button>
          </Card>
        </form>
      )}
      <Card title="Synthetic Model & Real Background Retraining">
        <div className="tight">
          <div className="row between">
            <div>
              <strong>
                {report
                  ? "Active model: " + report.version
                  : "Rule fallback · no trained model"}
              </strong>
              <p className="tiny muted">
                {report
                  ? `Trained ${localTime(report.trained_at)} · ${report.dataset_size} synthetic examples`
                  : "Run training to enable measured model probabilities."}
              </p>
            </div>
            <button
              className="button-primary"
              disabled={busy || training?.status === "RUNNING"}
              onClick={() => void retrain()}
            >
              <RefreshCw size={14} />
              {training?.status === "RUNNING"
                ? "Training job running…"
                : "Retrain Model"}
            </button>
          </div>
          <p className="tiny muted">
            Operator preferences are stored as feedback. Independently verified
            outcome labels are unavailable (0 usable labels); retraining uses
            the reproducible synthetic data, not approvals as ground truth.
          </p>
          {training && (
            <div className="notice slate" style={{ display: "block" }}>
              <div className="row">
                <Badge
                  tone={
                    training.status === "DONE"
                      ? "green"
                      : training.status === "FAILED"
                        ? "red"
                        : "amber"
                  }
                >
                  {training.status}
                </Badge>
                <span>{training.id}</span>
              </div>
              {training.result && (
                <details>
                  <summary>Actual job result / metrics</summary>
                  <pre>{JSON.stringify(training.result, null, 2)}</pre>
                </details>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function Simulation({
  onClose,
  done,
}: {
  onClose: () => void;
  done: (o: Order) => void;
}) {
  const [profile, setProfile] = useState("next"),
    [errorType, setErrorType] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const key = useRef(crypto.randomUUID());
  return (
    <Modal title="Simulate Live Order & Incident" onClose={onClose}>
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            done(
              await api<Order>(
                "/api/console/demo",
                { profile, error_type: errorType || null },
                key.current,
              ),
            );
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <p className="tiny muted">
          Creates a real persisted demo booking through the shared booking
          service. It appears in ShopEase My Orders in another localhost tab.
        </p>
        <label className="field">
          Scenario profile
          <select
            value={profile}
            onChange={(e) => {
              setProfile(e.target.value);
              key.current = crypto.randomUUID();
            }}
          >
            <option value="next">Next booking · current settings</option>
            <option value="judge">
              Judge five-order scripted error profile
            </option>
            <option value="exhaustion">
              Retry exhaustion fixture · 3 service failures
            </option>
          </select>
        </label>
        <label className="field">
          Explicit Error Override (optional)
          <select
            value={errorType}
            onChange={(e) => {
              setErrorType(e.target.value);
              key.current = crypto.randomUUID();
            }}
          >
            <option value="">Follow profile / settings</option>
            {errors.map((e) => (
              <option key={e} value={e}>
                {label(e)}
              </option>
            ))}
          </select>
        </label>
        <div className="notice">
          Judge profile selects healthy / timeout / healthy / insulin unmatched
          debit / stock issue by block position. It does not override model
          outputs or risk scores. Use a fresh demo database for positions 1–5.
        </div>
        <ErrorBox error={error} />
        <button className="button-primary" disabled={busy} type="submit">
          <Zap size={14} />
          {busy ? "Booking…" : "Run Next Booking"}
        </button>
      </form>
    </Modal>
  );
}
