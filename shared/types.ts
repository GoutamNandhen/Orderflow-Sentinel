export interface Product {
  id: string;
  name: string;
  category: string;
  price: number;
  stock: number;
  is_critical: boolean;
  description: string;
  icon: string;
}
export interface Forecast {
  delivery_minutes: number;
  delay_minutes: number;
  repair_seconds: number | null;
  sample_count: number;
  source: string;
  error_penalty_minutes: number;
}
export interface OrderItem {
  product_id: string;
  name: string;
  category: string;
  price: number;
  qty: number;
  is_critical: boolean;
}
export interface Order {
  id: string;
  user_name: string;
  phone: string;
  address: string;
  pincode: string;
  items: OrderItem[];
  amount: number;
  payment_method: string;
  priority: string;
  status: string;
  fulfilment: string;
  promised_by: string;
  created_at: string;
  updated_at: string;
  delivered_at: string | null;
  attempt_count: number;
  booking_seq: number;
  version: number;
  initial_failed: boolean;
  simulator_override: boolean;
  profile?: string;
  customer_message: string;
  incident_id?: string | null;
  incident_status: string | null;
  tracking_token?: string;
  payment: {
    status: string;
    amount: number;
    attempt_count: number;
    reconciled: boolean;
  };
  refund: { status: string; amount: number; settled_at: string | null } | null;
  pending_offer: {
    kind: string;
    message: string;
    address?: string;
    pincode?: string;
    promised_by?: string;
  } | null;
  forecast: Forecast;
  notifications: {
    id: number;
    kind: string;
    message: string;
    timestamp: string;
    late: boolean;
  }[];
}
export interface Page<T> {
  items: T[];
  total: number;
}
export interface Risk {
  score: number;
  tier: string;
  action: string;
  components: Record<string, number>;
  weights: Record<string, number>;
  contributions: Record<string, number>;
  charged_bump: number;
}
export interface ModelOutput {
  source: string;
  version: string | null;
  failure_probability: number | null;
  error_class: string | null;
  confidence: number | null;
  policy_confidence: number;
  anomaly_raw: number | null;
  anomaly_display: number | null;
  features?: Record<string, string | number>;
}
export interface Audit {
  id: number;
  action: string;
  done_by: string;
  attempt_no: number;
  result: string;
  before_status: string;
  after_status: string;
  note: string;
  timestamp: string;
}
export interface Job {
  id: string;
  kind: string;
  status: string;
  due_at: string;
  result: Record<string, unknown> | null;
  expected_version: number;
}
export interface Incident {
  id: string;
  order_id: string;
  error_type: string;
  message: string;
  detected_at: string;
  priority: string;
  risk_score: number;
  risk_tier: string;
  confidence: number;
  decision: string;
  suggested_action: string;
  status: string;
  resolved_at: string | null;
  resolved_by: string | null;
  time_to_fix_sec: number | null;
  version: number;
  order: Order;
  model_output: ModelOutput;
  risk_breakdown: Risk;
  forecast: Forecast;
  explanation: {
    operator: string[];
    customer: string;
    source: string;
    priority_reasons: string[];
    signals: string[];
  };
  actions?: Record<string, { enabled: boolean; reason: string | null }>;
  action_scores?: Record<string, { risk: Risk; decision: string }>;
  audit?: Audit[];
  jobs?: Job[];
  feedback?: {
    operator_decision: string;
    comment: string;
    chosen_action: string;
    timestamp: string;
  }[];
  playbook?: Record<string, unknown>;
}
export interface Settings {
  enabled: boolean;
  failing_positions: number[];
  selection: "rotation" | "weighted";
  seed: number;
  force_error: string | null;
  auto_confidence: number;
  auto_risk: number;
  high_value_paise: number;
  close_deadline_minutes: number;
  alert_fraction: number;
  retry_failures: number;
}
export interface DemoStatus {
  position: number;
  next_sequence: number;
  enabled: boolean;
  failing_positions: number[];
  forced_override_pending: boolean;
}
export interface LiveEvent {
  id: number;
  type: string;
  timestamp: string;
  entity_version: number;
  order_id: string | null;
  incident_id: string | null;
  data: Record<string, unknown>;
}
export interface ModelReport {
  version: string;
  trained_at: string;
  dataset_size: number;
  seed: number;
  splits: Record<string, number>;
  failure_metrics: Record<string, number>;
  class_metrics: { accuracy: number; macro_f1: number; log_loss: number };
  usable_labelled_feedback: number;
  feedback_note: string;
  limitations: string[];
}
export interface Stats {
  total_orders: number;
  initial_failures: number;
  initial_success_rate: number | null;
  recovered_orders: number;
  eventual_recovery_rate: number | null;
  open_incidents: number;
  open_p1: number;
  auto_resolved: number;
  average_resolution_seconds: number | null;
  money_at_risk_paise: number;
  errors_by_type: { name: string; count: number }[];
  trend: {
    hour: string;
    detected: number;
    recovered: number;
    mean_seconds: number | null;
  }[];
  handling: { name: string; count: number }[];
  risk_distribution: { name: string; count: number }[];
  events: LiveEvent[];
  model: ModelReport | null;
}
export interface Gateway {
  gateway_name: string;
  last_errors_1min: number;
  circuit_state: string;
  updated_at: string;
  opened_at: string | null;
  probe_claimed: boolean;
}
export const errors = [
  "API_TIMEOUT",
  "RATE_LIMIT",
  "TOKEN_EXPIRED",
  "ADDRESS_REJECTED",
  "PAYMENT_DECLINED",
  "UNMATCHED_DEBIT",
  "DUPLICATE_ORDER",
  "OUT_OF_STOCK",
  "STORE_CLOSED",
  "RIDER_LATE",
];
