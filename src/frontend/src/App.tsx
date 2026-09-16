import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ApiError,
  ask,
  checkInVisitor,
  getRoutingMode,
  requestAccess,
  setRoutingMode,
  type Citation,
  type ExecutionInfo,
  type RoutingMode,
  type RoutingModeState,
  type SecurityOperationResponse,
} from "./api";
import { ExecutionDetails } from "./ExecutionDetails";
import { RouterControl } from "./RouterControl";

const SAMPLE_QUESTION =
  "Why is Floor 3 energy-sensitive, and what is happening there now?";

type View = "assistant" | "security";
type AccessMethod = "badge" | "mobile";
type CallMode = "foundry" | "gateway";
type ScenarioKey = "general" | "quick" | "live" | "compliance";

interface OperationState {
  loading: boolean;
  error: ApiError | null;
  result: SecurityOperationResponse | null;
}

const EMPTY_OPERATION: OperationState = {
  loading: false,
  error: null,
  result: null,
};

const SCENARIOS: { key: ScenarioKey; label: string; scenario: string | null }[] = [
  { key: "general", label: "General", scenario: null },
  { key: "quick", label: "Quick lookup", scenario: "quick" },
  { key: "live", label: "Live operations", scenario: "live" },
  { key: "compliance", label: "Compliance analysis", scenario: "compliance" },
];

// A single turn in the Assistant conversation transcript. User turns are
// captured immediately; agent turns start "pending" and are updated in place
// once the response (or error) for that specific turn arrives, so a later or
// stale response can never be attributed to the wrong message.
interface ChatMessage {
  id: number;
  role: "user" | "agent";
  status: "done" | "pending" | "error";
  text?: string;
  citations?: Citation[];
  execution?: ExecutionInfo | null;
  errorMessage?: string;
}

function formatPropagationMessage(seconds?: number): string {
  if (!seconds || seconds <= 0) {
    return "Routing mode updated.";
  }
  const duration = seconds >= 60 ? `${Math.round(seconds / 60)} min` : `${seconds} s`;
  return `Routing mode updated. Allow up to ${duration} to propagate.`;
}

export function App() {
  const [view, setView] = useState<View>("assistant");
  const [question, setQuestion] = useState(SAMPLE_QUESTION);
  const [callMode, setCallMode] = useState<CallMode>("foundry");
  const [scenario, setScenario] = useState<ScenarioKey>("live");
  const [conversations, setConversations] = useState<Record<CallMode, ChatMessage[]>>({
    foundry: [],
    gateway: [],
  });
  const [loading, setLoading] = useState(false);
  const [routing, setRouting] = useState<RoutingModeState | null>(null);
  const [routingLoading, setRoutingLoading] = useState(true);
  const [routingBusy, setRoutingBusy] = useState(false);
  const [routingMessage, setRoutingMessage] = useState<string | null>(null);
  const [accessMethod, setAccessMethod] = useState<AccessMethod>("badge");
  const [accessState, setAccessState] = useState<OperationState>(EMPTY_OPERATION);
  const [visitorState, setVisitorState] = useState<OperationState>(EMPTY_OPERATION);
  const credentialId = accessMethod === "badge" ? "BDG-1042" : "MOB-2048";
  const nextMessageId = useRef(0);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const messages = conversations[callMode];

  useEffect(() => {
    let cancelled = false;
    setRoutingLoading(true);
    getRoutingMode()
      .then((state) => {
        if (!cancelled) setRouting(state);
      })
      .catch(() => {
        if (!cancelled) setRouting(null);
      })
      .finally(() => {
        if (!cancelled) setRoutingLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const node = transcriptRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages]);

  async function onRoutingChange(mode: RoutingMode) {
    setRoutingBusy(true);
    setRoutingMessage(null);
    try {
      const updated = await setRoutingMode(mode);
      setRouting(updated);
      setRoutingMessage(formatPropagationMessage(updated.propagation_seconds));
    } catch (err) {
      setRoutingMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setRoutingBusy(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;

    const mode = callMode;
    const scenarioValue =
      mode === "gateway" ? "governed" : SCENARIOS.find((option) => option.key === scenario)?.scenario ?? null;
    const userMessageId = nextMessageId.current++;
    const agentMessageId = nextMessageId.current++;

    setConversations((prev) => ({
      ...prev,
      [mode]: [
        ...prev[mode],
        { id: userMessageId, role: "user", status: "done", text: trimmed },
        { id: agentMessageId, role: "agent", status: "pending" },
      ],
    }));
    setLoading(true);
    try {
      const response = await ask(trimmed, scenarioValue);
      setConversations((prev) => ({
        ...prev,
        [mode]: prev[mode].map((message) =>
          message.id === agentMessageId
            ? {
                ...message,
                status: "done",
                text: response.answer,
                citations: response.citations,
                execution: response.execution ?? null,
              }
            : message,
        ),
      }));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      setConversations((prev) => ({
        ...prev,
        [mode]: prev[mode].map((message) =>
          message.id === agentMessageId ? { ...message, status: "error", errorMessage } : message,
        ),
      }));
    } finally {
      setLoading(false);
    }
  }

  async function onAccessRequest(event: FormEvent) {
    event.preventDefault();
    setAccessState({ loading: true, error: null, result: null });
    try {
      const accessResult = await requestAccess({
        building_id: "paris-hq",
        access_point_id: "main-lobby",
        credential_id: credentialId,
        method: accessMethod,
      });
      setAccessState({ loading: false, error: null, result: accessResult });
    } catch (requestError) {
      const apiError =
        requestError instanceof ApiError
          ? requestError
          : new ApiError(String(requestError), 500);
      setAccessState({ loading: false, error: apiError, result: null });
    }
  }

  async function onVisitorCheckIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setVisitorState({ loading: true, error: null, result: null });
    try {
      const visitorResult = await checkInVisitor({
        building_id: "paris-hq",
        access_point_id: "main-lobby",
        visitor_name: String(form.get("visitor_name")),
        visitor_email: String(form.get("visitor_email")),
        host_name: String(form.get("host_name")),
        purpose: String(form.get("purpose")),
      });
      setVisitorState({ loading: false, error: null, result: visitorResult });
    } catch (requestError) {
      const apiError =
        requestError instanceof ApiError
          ? requestError
          : new ApiError(String(requestError), 500);
      setVisitorState({ loading: false, error: apiError, result: null });
    }
  }

  function operationFeedback(state: OperationState, successMessage: string) {
    if (state.error) {
      return (
        <div className="operation-feedback operation-feedback--error" role="alert">
          <strong>{state.error.status} · Access service unavailable</strong>
          <span>{state.error.message}</span>
          {state.error.incidentId && <code>{state.error.incidentId}</code>}
        </div>
      );
    }
    if (state.result) {
      return (
        <div className="operation-feedback operation-feedback--success" role="status">
          <strong>{successMessage}</strong>
          <span>Reference {state.result.id}</span>
        </div>
      );
    }
    return null;
  }

  return (
    <main className="app">
      <header>
        <div>
          <h1>BuildingAssist</h1>
          <p className="subtitle">Contoso Energy · Smart Building operations</p>
        </div>
      </header>

      <nav className="view-tabs" aria-label="BuildingAssist views">
        <button
          type="button"
          className={view === "assistant" ? "active" : ""}
          onClick={() => setView("assistant")}
        >
          Assistant
        </button>
        <button
          type="button"
          className={view === "security" ? "active" : ""}
          onClick={() => setView("security")}
        >
          Security &amp; access
        </button>
      </nav>

      {view === "assistant" ? (
        <section className="view-panel" aria-labelledby="assistant-title">
          <div className="section-heading">
            <p className="eyebrow">Building intelligence</p>
            <h2 id="assistant-title">Ask about operations</h2>
          </div>

          <div className="composer">
            <div className="mode-bar">
              <div className="segmented-control mode-toggle">
                <button
                  type="button"
                  className={callMode === "foundry" ? "active" : ""}
                  aria-pressed={callMode === "foundry"}
                  onClick={() => setCallMode("foundry")}
                >
                  Foundry
                </button>
                <button
                  type="button"
                  className={callMode === "gateway" ? "active" : ""}
                  aria-pressed={callMode === "gateway"}
                  onClick={() => setCallMode("gateway")}
                >
                  AI Gateway
                </button>
              </div>
              {callMode === "foundry" && (
                <label className="agent-picker">
                  Agent
                  <select
                    value={scenario}
                    onChange={(event) => setScenario(event.target.value as ScenarioKey)}
                  >
                    {SCENARIOS.map((option) => (
                      <option key={option.key} value={option.key}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>

            <form onSubmit={onSubmit} className="ask-form">
              <input
                type="text"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder={SAMPLE_QUESTION}
                aria-label="Building question"
              />
              <RouterControl
                routing={routing}
                loading={routingLoading}
                busy={routingBusy}
                message={routingMessage}
                onChange={onRoutingChange}
              />
              <button type="submit" disabled={loading || question.trim().length === 0}>
                {loading ? "Asking…" : "Ask"}
              </button>
            </form>
          </div>

          <div
            className="chat-transcript"
            role="log"
            aria-label="Conversation history"
            aria-live="polite"
            tabIndex={0}
            ref={transcriptRef}
          >
            {messages.length === 0 && (
              <p className="chat-empty">Ask a question to start the conversation.</p>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`chat-message chat-message--${message.role}`}
                data-status={message.status}
              >
                <span className="chat-message__speaker">
                  {message.role === "user" ? "You" : "Assistant"}
                </span>
                <div className="chat-message__body">
                  {message.role === "user" && <p>{message.text}</p>}
                  {message.role === "agent" && message.status === "pending" && (
                    <p className="chat-message__pending" role="status">
                      Asking the building agent…
                    </p>
                  )}
                  {message.role === "agent" && message.status === "error" && (
                    <p className="chat-message__error" role="alert">
                      {message.errorMessage}
                    </p>
                  )}
                  {message.role === "agent" && message.status === "done" && (
                    <>
                      <div className="markdown-body">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.text ?? ""}
                        </ReactMarkdown>
                      </div>

                      {message.citations && message.citations.length > 0 && (
                        <div className="citations">
                          <h3>Sources</h3>
                          <ul>
                            {message.citations.map((citation, index) => (
                              <li key={index}>
                                {citation.url ? (
                                  <a href={citation.url} target="_blank" rel="noreferrer">
                                    {citation.title || citation.url}
                                  </a>
                                ) : (
                                  <span>{citation.title}</span>
                                )}
                                {citation.snippet && <p className="snippet">{citation.snippet}</p>}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <ExecutionDetails execution={message.execution} />
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="view-panel" aria-labelledby="security-title">
          <div className="section-heading section-heading--security">
            <div>
              <p className="eyebrow">Live access operations</p>
              <h2 id="security-title">Security &amp; Access Control</h2>
            </div>
            <span className="system-status">Monitoring enabled</span>
          </div>

          <div className="security-grid">
            <form className="operation-card" onSubmit={onAccessRequest}>
              <div className="operation-card__heading">
                <span className="operation-index">01</span>
                <div>
                  <h3>Employee access</h3>
                  <p>Validate an active credential at the main lobby.</p>
                </div>
              </div>

              <fieldset>
                <legend>Credential type</legend>
                <div className="segmented-control">
                  <button
                    type="button"
                    className={accessMethod === "badge" ? "active" : ""}
                    onClick={() => setAccessMethod("badge")}
                  >
                    Badge
                  </button>
                  <button
                    type="button"
                    className={accessMethod === "mobile" ? "active" : ""}
                    onClick={() => setAccessMethod("mobile")}
                  >
                    Mobile
                  </button>
                </div>
              </fieldset>

              <label>
                Credential
                <input
                  value={credentialId}
                  readOnly
                />
              </label>
              <label>
                Access point
                <input value="Main lobby" readOnly />
              </label>
              <button className="primary-action" type="submit" disabled={accessState.loading}>
                {accessState.loading ? "Validating…" : "Request access"}
              </button>
              {operationFeedback(accessState, "Access granted")}
            </form>

            <form className="operation-card" onSubmit={onVisitorCheckIn}>
              <div className="operation-card__heading">
                <span className="operation-index">02</span>
                <div>
                  <h3>Visitor check-in</h3>
                  <p>Register a guest and issue a temporary lobby pass.</p>
                </div>
              </div>

              <div className="field-row">
                <label>
                  Visitor
                  <input name="visitor_name" defaultValue="Jordan Lee" required />
                </label>
                <label>
                  Email
                  <input
                    name="visitor_email"
                    type="email"
                    defaultValue="jordan.lee@example.com"
                    required
                  />
                </label>
              </div>
              <label>
                Host
                <input name="host_name" defaultValue="Morgan Chen" required />
              </label>
              <label>
                Purpose
                <input name="purpose" defaultValue="Energy audit" required />
              </label>
              <button className="primary-action" type="submit" disabled={visitorState.loading}>
                {visitorState.loading ? "Checking in…" : "Check in visitor"}
              </button>
              {operationFeedback(visitorState, "Visitor checked in")}
            </form>
          </div>
        </section>
      )}
    </main>
  );
}
