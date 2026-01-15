import React, { useEffect, useMemo, useState } from "react";

function normalizeApiBase(raw) {
  if (!raw) return "http://127.0.0.1:8000";
  // Prevent cookie split-brain: localhost and 127.0.0.1 are different cookie sites.
  // Force 127.0.0.1 everywhere in dev.
  return raw
    .replace("http://localhost", "http://127.0.0.1")
    .replace("https://localhost", "https://127.0.0.1");
}

const API_BASE = normalizeApiBase(import.meta.env.VITE_API_BASE);

function toLocalInputValue(date) {
  // yyyy-MM-ddTHH:mm for <input type="datetime-local">
  const pad = (n) => String(n).padStart(2, "0");
  const yyyy = date.getFullYear();
  const mm = pad(date.getMonth() + 1);
  const dd = pad(date.getDate());
  const hh = pad(date.getHours());
  const mi = pad(date.getMinutes());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

function localInputToISOWithOffset(localValue) {
  // localValue is yyyy-MM-ddTHH:mm (no timezone)
  // Convert to ISO with local timezone offset (e.g., 2026-01-14T12:17:00+07:00)
  const d = new Date(localValue);
  const pad = (n) => String(n).padStart(2, "0");
  const yyyy = d.getFullYear();
  const mm = pad(d.getMonth() + 1);
  const dd = pad(d.getDate());
  const hh = pad(d.getHours());
  const mi = pad(d.getMinutes());
  const ss = "00";

  const offsetMin = -d.getTimezoneOffset(); // minutes east of UTC
  const sign = offsetMin >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMin);
  const offH = pad(Math.floor(abs / 60));
  const offM = pad(abs % 60);

  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}${sign}${offH}:${offM}`;
}

async function fetchJSON(url, options = {}) {
  // Use the top-level normalized API_BASE (do NOT redeclare a new one here)
  const fullUrl = url.startsWith("http") ? url : `${API_BASE}${url}`;

  const headers = new Headers(options.headers || {});
  const hasBody = options.body !== undefined && options.body !== null;

  // If sending a body and Content-Type isn't set, assume JSON
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // Prefer JSON responses
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const res = await fetch(fullUrl, {
    credentials: "include",
    ...options,
    headers,
  });

  // Read response safely (JSON if possible, otherwise text)
  const contentType = res.headers.get("content-type") || "";
  let data;
  if (contentType.includes("application/json")) {
    data = await res.json().catch(() => null);
  } else {
    data = await res.text().catch(() => "");
  }

  if (!res.ok) {
    // Make FastAPI errors readable
    let msg = `HTTP ${res.status}`;
    if (data) {
      if (typeof data === "string") {
        msg = data || msg;
      } else if (Array.isArray(data.detail)) {
        // FastAPI validation errors
        msg = data.detail
          .map((e) => `${(e.loc || []).join(".")}: ${e.msg}`)
          .join(" | ");
      } else if (typeof data.detail === "string") {
        msg = data.detail;
      } else if (data.error) {
        msg = data.error;
      } else {
        msg = JSON.stringify(data);
      }
    }
    throw new Error(msg);
  }

  return data;
}

export default function App() {
  const [error, setError] = useState("");
  const [health, setHealth] = useState(null);

  // FreeBusy
  const now = useMemo(() => new Date(), []);
  const [fbStartLocal, setFbStartLocal] = useState(toLocalInputValue(now));
  const [fbEndLocal, setFbEndLocal] = useState(toLocalInputValue(new Date(now.getTime() + 2 * 60 * 60 * 1000)));
  const [freeBusyResult, setFreeBusyResult] = useState(null);

  // Propose
  const [pStartLocal, setPStartLocal] = useState(toLocalInputValue(new Date(now.getTime() + 30 * 60 * 1000)));
  const [pEndLocal, setPEndLocal] = useState(toLocalInputValue(new Date(now.getTime() + 2.5 * 60 * 60 * 1000)));
  const [durationMin, setDurationMin] = useState(30);
  const [limit, setLimit] = useState(5);
  const [proposals, setProposals] = useState(null);

  // AI plan
  const [prompt, setPrompt] = useState("Schedule a 30 minute meeting tomorrow afternoon");
  const [plan, setPlan] = useState(null);

  useEffect(() => {
    setError("");
  }, []);

  const handleHealth = async () => {
    try {
      setError("");
      const data = await fetchJSON("/health", { method: "GET" });
      setHealth(data);
    } catch (e) {
      setHealth(null);
      setError(String(e.message || e));
    }
  };

  const handleSignIn = () => {
    // Important: OAuth should be started by a TOP-LEVEL navigation, not fetch().
    // This ensures the session cookie is set on the same host that receives the callback.
    window.location.href = `${API_BASE}/auth/google/login`;
  };

  const handleCreateTestEvent = async () => {
    try {
      setError("");
      const data = await fetchJSON("/calendar/test-event", { method: "GET" });
      // show success in UI
      setPlan({ ok: true, created: data });
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const handleFreeBusy = async () => {
    try {
      setError("");
      const start = localInputToISOWithOffset(fbStartLocal);
      const end = localInputToISOWithOffset(fbEndLocal);
      const data = await fetchJSON("/calendar/freebusy", {
        method: "POST",
        body: JSON.stringify({ start, end }),
      });
      setFreeBusyResult(data);
    } catch (e) {
      setFreeBusyResult(null);
      setError(String(e.message || e));
    }
  };

  const handlePropose = async () => {
    try {
      setError("");
      const start = localInputToISOWithOffset(pStartLocal);
      const end = localInputToISOWithOffset(pEndLocal);
      const data = await fetchJSON("/ai/propose", {
        method: "POST",
        body: JSON.stringify({
          start,
          end,
          duration_minutes: Number(durationMin),
          limit: Number(limit),
        }),
      });
      setProposals(data);
    } catch (e) {
      setProposals(null);
      setError(String(e.message || e));
    }
  };

  const handlePlan = async () => {
    try {
      setError("");
      const data = await fetchJSON("/ai/plan", {
        method: "POST",
        body: JSON.stringify({ prompt, limit: Number(limit) }),
      });
      setPlan(data);
    } catch (e) {
      setPlan(null);
      setError(String(e.message || e));
    }
  };

  const fbStartISO = localInputToISOWithOffset(fbStartLocal);
  const fbEndISO = localInputToISOWithOffset(fbEndLocal);
  const pStartISO = localInputToISOWithOffset(pStartLocal);
  const pEndISO = localInputToISOWithOffset(pEndLocal);

  return (
    <div style={{ padding: 24, maxWidth: 980, margin: "0 auto", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial" }}>
      <h1 style={{ marginBottom: 8 }}>GG Calendar AI — Phase 3 (Local Time UI)</h1>
      <div style={{ fontSize: 12, color: "#555", marginBottom: 12 }}>API_BASE: {API_BASE}</div>

      {/* Core */}
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>Core controls</h2>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button onClick={handleHealth}>Check backend /health</button>
          <button onClick={handleSignIn}>Sign in with Google</button>
          <button onClick={handleCreateTestEvent}>Create test event</button>
        </div>
        <div style={{ marginTop: 12, fontSize: 14 }}>
          {health ? <pre style={{ background: "#f7f7f7", padding: 12, borderRadius: 8 }}>{JSON.stringify(health, null, 2)}</pre> : <div>No health data yet.</div>}
        </div>
      </section>

      {/* FreeBusy */}
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>Pick a window (FreeBusy)</h2>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, maxWidth: 700 }}>
          <label>
            Start (local)
            <input type="datetime-local" value={fbStartLocal} onChange={(e) => setFbStartLocal(e.target.value)} style={{ display: "block", width: "100%" }} />
          </label>
          <label>
            End (local)
            <input type="datetime-local" value={fbEndLocal} onChange={(e) => setFbEndLocal(e.target.value)} style={{ display: "block", width: "100%" }} />
          </label>
        </div>
        <button style={{ marginTop: 12 }} onClick={handleFreeBusy}>
          Check FreeBusy
        </button>
        <div style={{ marginTop: 12, fontSize: 14 }}>
          <div><b>Start ISO (sent to backend):</b> {fbStartISO}</div>
          <div><b>End ISO (sent to backend):</b> {fbEndISO}</div>
        </div>
        {freeBusyResult && (
          <pre style={{ background: "#f7f7f7", padding: 12, borderRadius: 8, marginTop: 12 }}>
            {JSON.stringify(freeBusyResult, null, 2)}
          </pre>
        )}
      </section>

      {/* Propose */}
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>AI propose (shows Local time)</h2>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, maxWidth: 700 }}>
          <label>
            Window start (local)
            <input type="datetime-local" value={pStartLocal} onChange={(e) => setPStartLocal(e.target.value)} style={{ display: "block", width: "100%" }} />
          </label>
          <label>
            Window end (local)
            <input type="datetime-local" value={pEndLocal} onChange={(e) => setPEndLocal(e.target.value)} style={{ display: "block", width: "100%" }} />
          </label>
          <label>
            Duration (minutes)
            <input type="number" value={durationMin} onChange={(e) => setDurationMin(e.target.value)} style={{ display: "block", width: "100%" }} />
          </label>
          <label>
            Limit (how many suggestions)
            <input type="number" value={limit} onChange={(e) => setLimit(e.target.value)} style={{ display: "block", width: "100%" }} />
          </label>
        </div>
        <button style={{ marginTop: 12 }} onClick={handlePropose}>
          Propose slots
        </button>
        <div style={{ marginTop: 12, fontSize: 14 }}>
          <div><b>Start ISO (sent to backend):</b> {pStartISO}</div>
          <div><b>End ISO (sent to backend):</b> {pEndISO}</div>
        </div>
        {proposals && (
          <pre style={{ background: "#f7f7f7", padding: 12, borderRadius: 8, marginTop: 12 }}>
            {JSON.stringify(proposals, null, 2)}
          </pre>
        )}
      </section>

      {/* Plan */}
      <section style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>AI plan (natural language)</h2>
        <label style={{ display: "block", maxWidth: 700 }}>
          Prompt
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} style={{ display: "block", width: "100%" }} />
        </label>
        <button style={{ marginTop: 12 }} onClick={handlePlan}>
          Plan with AI
        </button>
        {plan && (
          <pre style={{ background: "#f7f7f7", padding: 12, borderRadius: 8, marginTop: 12 }}>
            {JSON.stringify(plan, null, 2)}
          </pre>
        )}
      </section>

      {error && (
        <div style={{ border: "1px solid #f5c2c7", background: "#f8d7da", color: "#842029", padding: 12, borderRadius: 10 }}>
          ERROR: {error}
        </div>
      )}
    </div>
  );
}
