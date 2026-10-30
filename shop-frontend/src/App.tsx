import { useEffect, useRef, useState, type FormEvent } from "react";
import * as Icons from "lucide-react";
import {
  Syringe,
  Baby,
  Headphones,
  Pill,
  Wheat,
  HeartPulse,
  Shirt,
  Milk,
  FlaskConical,
  Thermometer,
  Apple,
  Plug,
  Mouse,
  Speaker,
  ShoppingBag,
} from "lucide-react";
import { api, useLive, useResource } from "../../shared/api";
import type { Order, Page, Product, DemoStatus } from "../../shared/types";
import {
  Badge,
  Card,
  Connection,
  Empty,
  ErrorBox,
  Switcher,
  Toast,
  money,
  localTime,
  label,
  Pager,
} from "../../shared/ui";

const productIcons: Record<string, Icons.LucideIcon> = {
  Syringe,
  Baby,
  Headphones,
  Pill,
  Wheat,
  HeartPulse,
  Shirt,
  Milk,
  FlaskConical,
  Thermometer,
  Apple,
  Plug,
  Mouse,
  Speaker,
  ShoppingBag,
};
function ProductIcon({ product }: { product: Product }) {
  const Icon = productIcons[product.icon] || Icons.Package;
  return (
    <div className={`product-icon ${product.category.split(" ")[0]}`}>
      <Icon size={25} strokeWidth={1.6} />
    </div>
  );
}

export default function App() {
  const params = new URLSearchParams(location.search);
  const [demoContact, setDemoContact] = useState(true);
  const [view, setView] = useState(params.get("order") ? "tracking" : "store"),
    [category, setCategory] = useState("All"),
    [search, setSearch] = useState("");
  const [cart, setCart] = useState<Record<string, number>>(() => {
    try {
      return JSON.parse(localStorage.getItem("shop_cart") || "{}");
    } catch {
      return {};
    }
  });
  const [active, setActive] = useState(params.get("order") || ""),
    [trackingToken, setTrackingToken] = useState(params.get("token") || "");
  const [toast, setToast] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [offset, setOffset] = useState(0);
  const products = useResource<Product[]>("/api/products", 10000),
    orders = useResource<Page<Order>>(
      `/api/orders?offset=${offset}&limit=25`,
      5000,
    );
  const tracking = useResource<Order>(
    active
      ? `/api/orders/${active}${trackingToken ? "?token=" + encodeURIComponent(trackingToken) : ""}`
      : null,
    5000,
  );
  const demo = useResource<DemoStatus>("/api/demo/status", 3000);
  const key = useRef<string | null>(null),
    lastBody = useRef("");
  const state = useLive(
    active && trackingToken
      ? `/ws/order/${active}?token=${encodeURIComponent(trackingToken)}`
      : null,
    () => {
      void tracking.refresh();
      void orders.refresh();
      void products.refresh();
    },
  );
  useEffect(() => {
    localStorage.setItem("shop_cart", JSON.stringify(cart));
  }, [cart]);
  const cartProducts = (products.data || []).filter((p) => cart[p.id] > 0),
    total = cartProducts.reduce((s, p) => s + p.price * cart[p.id], 0),
    qty = Object.values(cart).reduce((a, b) => a + b, 0);
  const selectOrder = (order: Order) => {
    setActive(order.id);
    setTrackingToken(order.tracking_token || "");
    setView("tracking");
  };
  const changeQty = (id: string, delta: number) =>
    setCart((old) => {
      const next = { ...old, [id]: Math.max(0, (old[id] || 0) + delta) };
      if (!next[id]) delete next[id];
      return next;
    });
  async function checkout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!qty) return;
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const body = {
      user_name: form.get("name"),
      phone: demoContact
        ? "DEMO_CONTACT"
        : String(form.get("phone")).replace(/[\s-]/g, ""),
      address: demoContact ? "DEMO_LOCATION" : form.get("address"),
      contact_mode: demoContact ? "demo" : "customer",
      pincode: form.get("pincode"),
      payment_method: form.get("payment"),
      promise_minutes: Number(form.get("promise")),
      items: cartProducts.map((p) => ({ product_id: p.id, qty: cart[p.id] })),
    };
    const fingerprint = JSON.stringify(body);
    if (fingerprint !== lastBody.current || !key.current) {
      lastBody.current = fingerprint;
      key.current = crypto.randomUUID();
    }
    try {
      const order = await api<Order>("/api/orders", body, key.current);
      setCart({});
      key.current = null;
      selectOrder(order);
      void orders.refresh();
      void products.refresh();
      setToast(
        `Booking ${order.id} accepted · position #${((order.booking_seq - 1) % 5) + 1} of 5`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function accept(yes: boolean) {
    if (!tracking.data) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/orders/${active}/accept`, {
        accept: yes,
        expected_version: tracking.data.version,
      });
      void tracking.refresh();
      void orders.refresh();
      void products.refresh();
      setToast(
        yes
          ? "Your accepted change was applied."
          : "Offer declined; operator review requested.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Switcher app="shop" state={state} />
      <nav className="shop-nav" aria-label="Shop navigation">
        <div className="nav-inner">
          <a href="#store" onClick={() => setView("store")} className="brand">
            <div className="brand-icon">
              <Icons.ShoppingBasket size={22} />
            </div>
            <div className="brand-title">
              Shop<em>Ease</em>
              <small>Express India Storefront</small>
            </div>
          </a>
          <div className="location">
            <Icons.MapPin size={16} color="#f59e0b" />
            <div>
              <small className="muted">Demo service area</small>
              <br />
              Indiranagar, Bengaluru 560038
            </div>
          </div>
          <div className="nav-search">
            <input
              aria-label="Search products"
              placeholder="Search medicines, baby food, electronics, groceries…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setView("store");
              }}
            />
          </div>
          <div className="nav-actions">
            <button onClick={() => setView("tracking")}>
              <Icons.Truck size={14} />
              Live Tracking
            </button>
            <button onClick={() => setView("orders")}>
              <Icons.Package size={14} />
              My Orders <Badge>{orders.data?.total || 0}</Badge>
            </button>
            <button className="button-gold" onClick={() => setView("checkout")}>
              <Icons.ShoppingCart size={14} />
              Cart <Badge>{qty}</Badge>
            </button>
          </div>
        </div>
        <div className="categories">
          <div className="category-inner">
            <span className="muted tiny">Categories:</span>
            {[
              "All",
              "Medicines",
              "Baby Food",
              "Food",
              "Electronics",
              "Clothes",
            ].map((cat) => (
              <button
                className={category === cat ? "selected" : ""}
                key={cat}
                onClick={() => {
                  setCategory(cat);
                  setView("store");
                }}
              >
                {cat === "All"
                  ? "All Items"
                  : cat === "Food"
                    ? "Food & Groceries"
                    : cat}
              </button>
            ))}
          </div>
        </div>
      </nav>
      <main id="main" className="shop-main stack">
        <ErrorBox
          error={products.error || orders.error || error}
          retry={() => {
            void products.refresh();
            void orders.refresh();
            setError("");
          }}
        />
        {view === "store" && (
          <>
            <div className="value-strip">
              <div className="brand-icon">
                <Icons.Zap size={22} />
              </div>
              <div className="grow">
                <h2>
                  Express Urban Fulfilment · Protected by OrderFlow Sentinel
                </h2>
                <p>
                  Medicines, infant nutrition and everyday essentials with
                  proactive incident recovery.
                </p>
                <p>
                  Local simulation · no real payments, messages, deliveries or
                  cold-chain fulfilment.
                </p>
              </div>
              {active && (
                <button onClick={() => setView("tracking")}>
                  Track {active} <Icons.ArrowRight size={13} />
                </button>
              )}
            </div>
            <section>
              <div className="section-title">
                <h2>
                  {category === "All"
                    ? "All Available Products"
                    : category + " Catalogue"}
                </h2>
                <span className="muted tiny">
                  {products.data?.filter(
                    (p) =>
                      (category === "All" || p.category === category) &&
                      `${p.name} ${p.description} ${p.category}`
                        .toLowerCase()
                        .includes(search.toLowerCase()),
                  ).length || 0}{" "}
                  products
                </span>
              </div>
              {products.loading ? (
                <div className="loading">Loading catalogue…</div>
              ) : (
                <div className="product-grid">
                  {products.data
                    ?.filter(
                      (p) =>
                        (category === "All" || p.category === category) &&
                        `${p.name} ${p.description} ${p.category}`
                          .toLowerCase()
                          .includes(search.toLowerCase()),
                    )
                    .map((p) => (
                      <article className="product-card" key={p.id}>
                        <div>
                          <div className="row between">
                            <ProductIcon product={p} />
                            <Badge tone={p.stock ? "green" : "red"}>
                              {p.stock
                                ? `In stock (${p.stock})`
                                : "Out of stock"}
                            </Badge>
                          </div>
                          <div className="product-category">
                            {p.category} {p.is_critical && " · CRITICAL"}
                          </div>
                          <h3>{p.name}</h3>
                          <p>{p.description}</p>
                        </div>
                        <div className="product-bottom">
                          <div>
                            <small className="muted">MRP (Incl. taxes)</small>
                            <div className="product-price">
                              {money(p.price)}
                            </div>
                          </div>
                          <button
                            className="button-primary"
                            disabled={
                              !p.stock ||
                              (cart[p.id] || 0) >= Math.min(p.stock, 20)
                            }
                            onClick={() => {
                              changeQty(p.id, 1);
                              setToast(`${p.name} added to your cart`);
                            }}
                          >
                            <Icons.Plus size={13} />
                            {cart[p.id]
                              ? `In Cart (${cart[p.id]})`
                              : "Add to Cart"}
                          </button>
                        </div>
                      </article>
                    ))}
                </div>
              )}
              {!products.loading &&
                products.data &&
                !products.data.some(
                  (p) =>
                    (category === "All" || p.category === category) &&
                    p.name.toLowerCase().includes(search.toLowerCase()),
                ) && (
                  <Empty>
                    No matching products. Try another search or category.
                  </Empty>
                )}
            </section>
          </>
        )}
        {view === "checkout" && (
          <>
            <div className="section-title">
              <div>
                <h1>Cart & Express Checkout</h1>
                <p className="muted tiny">
                  Bookings stream into Sentinel and follow the persistent
                  simulator settings.
                </p>
              </div>
              <button onClick={() => setView("store")}>
                ← Continue Shopping
              </button>
            </div>
            {!qty ? (
              <Card>
                <Empty>
                  Your cart is empty. Add products to place a simulated order.
                </Empty>
                <button onClick={() => setView("store")}>
                  Browse products
                </button>
              </Card>
            ) : (
              <form onSubmit={checkout}>
                <div className="two-columns">
                  <div className="stack">
                    <Card
                      title="1. Review Items in Cart"
                      action={
                        <button
                          className="button-link"
                          type="button"
                          onClick={() => setCart({})}
                        >
                          Clear Cart
                        </button>
                      }
                    >
                      {cartProducts.map((p) => (
                        <div className="cart-line" key={p.id}>
                          <div className="row grow">
                            <ProductIcon product={p} />
                            <div className="grow">
                              <h4>{p.name}</h4>
                              <p className="tiny muted">
                                {money(p.price)} per unit · {p.category}
                              </p>
                            </div>
                          </div>
                          <div className="quantity">
                            <button
                              type="button"
                              aria-label={`Remove one ${p.name}`}
                              onClick={() => changeQty(p.id, -1)}
                            >
                              −
                            </button>
                            <span>{cart[p.id]}</span>
                            <button
                              type="button"
                              aria-label={`Add one ${p.name}`}
                              disabled={cart[p.id] >= Math.min(20, p.stock)}
                              onClick={() => changeQty(p.id, 1)}
                            >
                              +
                            </button>
                            <strong>{money(p.price * cart[p.id])}</strong>
                          </div>
                        </div>
                      ))}
                    </Card>
                    <Card title="2. Delivery Address & Promised Slot">
                      <label className="row" style={{ marginBottom: 16 }}>
                        <input
                          type="checkbox"
                          checked={demoContact}
                          onChange={(e) => setDemoContact(e.target.checked)}
                        />
                        Use anonymized demo contact · no personal details
                        required
                      </label>
                      <div className="form-grid">
                        <label>
                          Customer Full Name *
                          <input
                            name="name"
                            required
                            minLength={2}
                            maxLength={100}
                            defaultValue="Demo Shopper"
                            autoComplete="name"
                          />
                        </label>
                        <label>
                          Mobile Number (+91) *
                          <input
                            name="phone"
                            required={!demoContact}
                            disabled={demoContact}
                            pattern="(\+91)?[6-9][0-9]{9}"
                            defaultValue=""
                            placeholder={
                              demoContact
                                ? "DEMO_CONTACT"
                                : "Enter mobile number"
                            }
                            autoComplete="tel"
                          />
                        </label>
                        <label className="span-all">
                          Street Address & Landmark *
                          <input
                            name="address"
                            required={!demoContact}
                            disabled={demoContact}
                            minLength={8}
                            maxLength={400}
                            defaultValue=""
                            placeholder={
                              demoContact
                                ? "DEMO_LOCATION"
                                : "Enter delivery address"
                            }
                            autoComplete="street-address"
                          />
                        </label>
                        <label>
                          Pincode *
                          <input
                            name="pincode"
                            required
                            pattern="[1-9][0-9]{5}"
                            defaultValue="560038"
                            autoComplete="postal-code"
                          />
                        </label>
                        <label>
                          Delivery Promise
                          <select name="promise">
                            <option value="40">
                              Express · within 40 minutes
                            </option>
                            <option value="90">
                              Standard · within 90 minutes
                            </option>
                            <option value="1440">
                              Tomorrow · within 24 hours
                            </option>
                          </select>
                        </label>
                      </div>
                    </Card>
                    <Card title="3. Simulated Payment">
                      <label className="field">
                        Payment method
                        <select name="payment">
                          <option value="UPI">UPI (demo)</option>
                          <option value="CARD">Card (demo)</option>
                          <option value="WALLET">ShopEase Wallet (demo)</option>
                          <option value="COD">Cash on Delivery</option>
                        </select>
                      </label>
                      <p className="muted tiny" style={{ marginTop: 12 }}>
                        No real payment details are collected and no money
                        moves.
                      </p>
                    </Card>
                  </div>
                  <div>
                    <Card title="Order Summary">
                      <div className="summary-line">
                        <span>Items Subtotal</span>
                        <strong>{money(total)}</strong>
                      </div>
                      <div className="summary-line">
                        <span>Simulated Delivery</span>
                        <span style={{ color: "#059669" }}>FREE</span>
                      </div>
                      <div className="summary-line">
                        <span>Taxes</span>
                        <span>Included in product prices</span>
                      </div>
                      <div className="summary-line summary-total">
                        <span>Total Payable</span>
                        <span>{money(total)}</span>
                      </div>
                      <div
                        className="notice slate"
                        style={{ margin: "18px 0" }}
                      >
                        Demo simulator: next booking #
                        {demo.data?.position || "—"}/5.{" "}
                        {demo.data?.forced_override_pending
                          ? "An explicit one-time override is pending."
                          : "The backend allocates the final position atomically."}
                      </div>
                      <button
                        className="button-primary"
                        type="submit"
                        style={{ width: "100%", padding: 14 }}
                        disabled={busy}
                      >
                        {busy ? "Processing booking…" : "Place Order"}
                        <Icons.ArrowRight size={15} />
                      </button>
                    </Card>
                  </div>
                </div>
              </form>
            )}
          </>
        )}
        {view === "orders" && (
          <>
            <div className="section-title">
              <div>
                <h1>My Orders</h1>
                <p className="muted tiny">
                  Private customer-session history backed by the local database.
                </p>
              </div>
              <button
                className="button-primary"
                onClick={() => setView("store")}
              >
                + Place Another Order
              </button>
            </div>
            {orders.loading ? (
              <div className="loading">Loading your orders…</div>
            ) : !orders.data?.items.length ? (
              <Card>
                <Empty>
                  No orders yet. Your first booking will appear here.
                </Empty>
              </Card>
            ) : (
              orders.data.items.map((o) => (
                <Card key={o.id}>
                  <div className="row between">
                    <div className="grow tight">
                      <div className="row">
                        <strong>{o.id}</strong>
                        <Badge
                          tone={
                            o.incident_status &&
                            o.incident_status !== "RESOLVED"
                              ? "amber"
                              : "green"
                          }
                        >
                          {label(o.status)}
                        </Badge>
                        <Badge>{label(o.fulfilment)}</Badge>
                      </div>
                      <p>
                        {o.items.map((i) => `${i.qty}× ${i.name}`).join(", ")}
                      </p>
                      <p className="muted tiny">
                        {money(o.amount)} · {label(o.payment.status)} ·{" "}
                        {localTime(o.created_at)}
                      </p>
                      <p className="tiny">{o.customer_message}</p>
                    </div>
                    <button onClick={() => selectOrder(o)}>
                      Track Order <Icons.ArrowRight size={13} />
                    </button>
                  </div>
                </Card>
              ))
            )}
            <Pager
              offset={offset}
              total={orders.data?.total || 0}
              onChange={setOffset}
            />
          </>
        )}
        {view === "tracking" && (
          <div className="stack" style={{ maxWidth: 950, margin: "auto" }}>
            <div className="section-title">
              <h1>Live Order Tracking</h1>
              <Connection state={state} />
            </div>
            {orders.data && orders.data.items.length > 0 && (
              <label className="row">
                Select Order
                <select
                  aria-label="Select order to track"
                  value={active}
                  onChange={(e) => {
                    const order = orders.data?.items.find(
                      (o) => o.id === e.target.value,
                    );
                    if (order) selectOrder(order);
                  }}
                >
                  <option value="">Choose an order</option>
                  {orders.data.items.map((o) => (
                    <option value={o.id} key={o.id}>
                      {o.id} · {money(o.amount)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <ErrorBox
              error={tracking.error}
              retry={() => void tracking.refresh()}
            />
            {!active ? (
              <Card>
                <Empty>
                  Select a booking from My Orders to start tracking.
                </Empty>
                <button onClick={() => setView("orders")}>
                  Open My Orders
                </button>
              </Card>
            ) : tracking.loading ? (
              <div className="loading">Loading tracking details…</div>
            ) : (
              tracking.data && (
                <Tracking order={tracking.data} busy={busy} accept={accept} />
              )
            )}
          </div>
        )}
      </main>
      <footer className="footer">
        ShopEase × OrderFlow Sentinel · Local demonstration · No external
        fulfilment or financial services
      </footer>
      {toast && <Toast text={toast} onClose={() => setToast("")} />}
    </>
  );
}

function Tracking({
  order: o,
  busy,
  accept,
}: {
  order: Order;
  busy: boolean;
  accept: (yes: boolean) => void;
}) {
  const paid = ["CAPTURED", "NOT_REQUIRED"].includes(o.payment.status),
    confirmed = ["CONFIRMED", "RESOLVED"].includes(o.status),
    steps = [
      "Placed",
      "Payment verified",
      "Confirmed",
      "Packed",
      "Out for delivery",
      "Delivered",
    ];
  const reached = [
    true,
    paid,
    confirmed,
    ["PACKED", "OUT_FOR_DELIVERY", "DELIVERED"].includes(o.fulfilment),
    ["OUT_FOR_DELIVERY", "DELIVERED"].includes(o.fulfilment),
    o.fulfilment === "DELIVERED",
  ];
  return (
    <section className="card">
      <div className="tracking-head">
        <div className="row between">
          <div className="row">
            <h2>{o.id}</h2>
            <Badge tone={paid ? "green" : "amber"}>
              {label(o.payment.status)}
            </Badge>
            {o.refund && (
              <Badge tone={o.refund.status === "COMPLETED" ? "green" : "amber"}>
                Refund {o.refund.status}
              </Badge>
            )}
          </div>
          <strong style={{ fontSize: 22 }}>{money(o.amount)}</strong>
        </div>
        <p className="tiny muted" style={{ marginTop: 8 }}>
          {o.user_name} · {o.address} ({o.pincode})
        </p>
      </div>
      <div className="card-body stack">
        <dl className="order-grid">
          <div>
            <dt>Original Promised Delivery</dt>
            <dd>{localTime(o.promised_by)}</dd>
          </div>
          <div>
            <dt>Revised Delivery Estimate · not guaranteed</dt>
            <dd>
              {["CANCELLED", "REFUNDED"].includes(o.status)
                ? "Order cancelled"
                : o.delivered_at
                  ? "Delivered " + localTime(o.delivered_at)
                  : localTime(
                      new Date(
                        new Date(o.created_at).getTime() +
                          o.forecast.delivery_minutes * 60000,
                      ).toISOString(),
                    )}
            </dd>
          </div>
          <div>
            <dt>Order state</dt>
            <dd>{label(o.status)}</dd>
          </div>
          <div>
            <dt>Delivery state</dt>
            <dd>{label(o.fulfilment)}</dd>
          </div>
        </dl>
        <p className="tiny muted">
          Estimate source: {o.forecast.source}. Incident repair time:
          unavailable until completed.
        </p>
        <div className="timeline">
          {steps.map((step, i) => (
            <div className="timeline-step" key={step}>
              <div className={`timeline-circle ${reached[i] ? "done" : ""}`}>
                {reached[i] ? <Icons.Check size={16} /> : i + 1}
              </div>
              <strong>{step}</strong>
              <div className="muted tiny">
                {reached[i] ? "Completed" : "Pending"}
              </div>
            </div>
          ))}
        </div>
        <div
          className={`notice ${o.incident_status === "RESOLVED" ? "green" : ""}`}
        >
          <Icons.Headset size={20} />
          <div>
            <h4>Live Order Support Update</h4>
            <p>{o.customer_message}</p>
            <p className="tiny">
              Incident:{" "}
              {o.incident_status ? label(o.incident_status) : "No incident"} ·
              Booking position #{((o.booking_seq - 1) % 5) + 1}/5{" "}
              {o.simulator_override ? "· explicit demo override" : ""}
            </p>
          </div>
        </div>
        {o.pending_offer && (
          <div className="suggested tight">
            <Badge tone="amber">CUSTOMER ACCEPTANCE NEEDED</Badge>
            <h3>{label(o.pending_offer.kind)} proposal</h3>
            <p>{o.pending_offer.message}</p>
            {o.pending_offer.address && (
              <p>
                {o.pending_offer.address} · {o.pending_offer.pincode}
              </p>
            )}
            {o.pending_offer.promised_by && (
              <p>{localTime(o.pending_offer.promised_by)}</p>
            )}
            <div className="row">
              <button
                className="button-primary"
                disabled={busy}
                onClick={() => accept(true)}
              >
                Accept Change
              </button>
              <button disabled={busy} onClick={() => accept(false)}>
                Decline
              </button>
            </div>
          </div>
        )}
        <Card title="Items in this Order">
          {o.items.map((i) => (
            <div key={i.product_id} className="summary-line">
              <span>
                {i.qty}× {i.name}
              </span>
              <strong>{money(i.qty * i.price)}</strong>
            </div>
          ))}
        </Card>
        {o.notifications.length > 0 && (
          <Card title="In-app Notifications">
            <div className="tight">
              {o.notifications.map((n) => (
                <div key={n.id}>
                  <small className="muted">
                    {localTime(n.timestamp)}
                    {n.late ? " · recorded late" : ""}
                  </small>
                  <p>{n.message}</p>
                </div>
              ))}
            </div>
          </Card>
        )}
        <p className="tiny muted">
          Placed {localTime(o.created_at)} · {o.payment_method} · All payment,
          notification and delivery activity is simulated locally.
        </p>
      </div>
    </section>
  );
}
