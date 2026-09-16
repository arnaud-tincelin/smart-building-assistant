import { FormEvent, Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Bot, ShieldCheck } from "lucide-react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ApiError,
  ask,
  checkInVisitor,
  getRoutingMode,
  requestAccess,
  setRoutingMode,
  type AskMode,
  type AskResponse,
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

type TurnOutcome =
  | { status: "pending" }
  | { status: "completed"; response: AskResponse }
  | { status: "failed"; error: string }
  | { status: "cancelled" };

interface ChatTurn {
  id: number;
  question: string;
  outcome: TurnOutcome;
}

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

export function App() {
  const [view, setView] = useState<View>("assistant");
  const [mode, setMode] = useState<AskMode>("agents");
  const [question, setQuestion] = useState(SAMPLE_QUESTION);
  const [histories, setHistories] = useState<Record<AskMode, ChatTurn[]>>({
    agents: [],
    gateway: [],
  });
  const [loading, setLoading] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  const nextTurnId = useRef(0);
  const transcript = useRef<HTMLDivElement | null>(null);
  const scrollPositions = useRef({
    agents: { top: 0, following: true },
    gateway: { top: 0, following: true },
  });
  const [routing, setRouting] = useState<RoutingModeState | null>(null);
  const [routingLoading, setRoutingLoading] = useState(true);
  const [routingBusy, setRoutingBusy] = useState(false);
  const [routingError, setRoutingError] = useState<string | null>(null);
  const [routingMessage, setRoutingMessage] = useState<string | null>(null);
  const [routingRefresh, setRoutingRefresh] = useState(0);
  const [accessMethod, setAccessMethod] = useState<AccessMethod>("badge");
  const [accessState, setAccessState] = useState<OperationState>(EMPTY_OPERATION);
  const [visitorState, setVisitorState] = useState<OperationState>(EMPTY_OPERATION);
  const credentialId = accessMethod === "badge" ? "BDG-1042" : "MOB-2048";
  const turns = histories[mode];

  useLayoutEffect(() => {
    const region = transcript.current;
    if (!region) return;
    const position = scrollPositions.current[mode];
    region.scrollTop = position.following ? region.scrollHeight : position.top;
  }, [turns, mode, view]);

  useEffect(() => {
    if (mode !== "agents") return;
    const controller = new AbortController();
    setRoutingLoading(true);
    setRoutingError(null);
    getRoutingMode(controller.signal)
      .then((state) => {
        if (!controller.signal.aborted) setRouting(state);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setRouting(null);
          setRoutingError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setRoutingLoading(false);
      });
    return () => controller.abort();
  }, [mode, routingRefresh]);

  useEffect(() => () => activeRequest.current?.abort(), []);

  function changeMode(nextMode: AskMode) {
    if (nextMode === mode) return;
    activeRequest.current?.abort();
    activeRequest.current = null;
    setHistories((previous) => ({
      ...previous,
      [mode]: previous[mode].map((turn) => turn.outcome.status === "pending"
        ? { ...turn, outcome: { status: "cancelled" } }
        : turn),
    }));
    setLoading(false);
    setMode(nextMode);
  }

  async function changeRouting(nextMode: RoutingMode) {
    if (!routing?.editable || routingBusy || nextMode === routing.mode) return;
    setRoutingBusy(true);
    setRoutingMessage(null);
    try {
      const state = await setRoutingMode(nextMode);
      setRouting(state);
      const minutes = Math.ceil((state.propagation_seconds ?? 300) / 60);
      setRoutingMessage(`Router set to ${state.mode}. Allow up to ${minutes} min to apply for all agent users.`);
    } catch (err) {
      setRoutingMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setRoutingBusy(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (activeRequest.current || !question.trim() || (mode === "agents" && routingBusy)) return;
    const controller = new AbortController();
    const id = nextTurnId.current++;
    const submittedQuestion = question;
    activeRequest.current = controller;
    setLoading(true);
    setHistories((previous) => ({
      ...previous,
      [mode]: [...previous[mode], { id, question: submittedQuestion, outcome: { status: "pending" } }],
    }));
    function finish(outcome: TurnOutcome) {
      if (controller.signal.aborted || activeRequest.current !== controller) return;
      setHistories((previous) => ({
        ...previous,
        [mode]: previous[mode].map((turn) => turn.id === id ? { ...turn, outcome } : turn),
      }));
    }
    try {
      const response = await ask(submittedQuestion, mode, controller.signal);
      finish({ status: "completed", response });
    } catch (err) {
      finish({ status: "failed", error: err instanceof Error ? err.message : String(err) });
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
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
          <div className="call-modes" role="group" aria-label="Answer route">
            <button type="button" aria-pressed={mode === "agents"}
              onClick={() => changeMode("agents")}>
              <Bot size={18} aria-hidden="true" />
              Agents
            </button>
            <button type="button" aria-pressed={mode === "gateway"}
              onClick={() => changeMode("gateway")}>
              <ShieldCheck size={18} aria-hidden="true" />
              AI Gateway
            </button>
          </div>
          <p className="call-mode-description">
            {mode === "agents"
              ? "BuildingAssist agent with Foundry IQ knowledge and building operations tools."
              : "Direct gpt-5-mini calls through AI Gateway with read-only building tools. No agent, Model Router, or Foundry IQ."}
          </p>
          <div className="chat-history" role="log" aria-label="Conversation history"
            tabIndex={0} ref={transcript}
            onScroll={(event) => {
              const region = event.currentTarget;
              scrollPositions.current[mode] = {
                top: region.scrollTop,
                following: region.scrollHeight - region.clientHeight - region.scrollTop <= 48,
              };
            }}>
            {turns.length === 0 && <p className="chat-empty">Ask a question to start this conversation.</p>}
            {turns.map((turn) => (
              <Fragment key={turn.id}>
                <article className="user-message" aria-label="User message">
                  <h3>You</h3>
                  <p>{turn.question}</p>
                </article>
                {turn.outcome.status === "pending" && <p role="status">Asking…</p>}
                {turn.outcome.status === "failed" && (
                  <div className="error" role="alert">Request failed: {turn.outcome.error}</div>
                )}
                {turn.outcome.status === "cancelled" && (
                  <p role="status">Request cancelled after switching modes.</p>
                )}
                {turn.outcome.status === "completed" && (
                  <article className="answer" aria-label="Assistant reply">
                    <h3>Assistant</h3>
                    <div className="answer-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                        pre: ({ children }) => <pre tabIndex={0}>{children}</pre>,
                        table: ({ children }) => (
                          <div className="answer-table" role="region" aria-label="Answer table" tabIndex={0}>
                            <table>{children}</table>
                          </div>
                        ),
                      }}>
                        {turn.outcome.response.answer}
                      </ReactMarkdown>
                    </div>
                    <ExecutionDetails execution={turn.outcome.response.execution} />
                    {turn.outcome.response.citations.length > 0 && (
                      <div className="citations">
                        <h3>Sources</h3>
                        <ul>
                          {turn.outcome.response.citations.map((citation, index) => {
                            const url = defaultUrlTransform(citation.url);
                            return (
                              <li key={index}>
                                {url ? (
                                  <a href={url} target="_blank" rel="noreferrer">
                                    {citation.title || citation.url}
                                  </a>
                                ) : (
                                  <span>{citation.title || citation.url}</span>
                                )}
                                {citation.snippet && <p className="snippet">{citation.snippet}</p>}
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                  </article>
                )}
              </Fragment>
            ))}
          </div>
          <form onSubmit={onSubmit} className="ask-form">
            <input
              type="text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={SAMPLE_QUESTION}
              aria-label="Building question"
            />
            <div className="composer-actions">
              {mode === "agents" ? (
                <RouterControl routing={routing} loading={routingLoading}
                  busy={routingBusy || loading} onChange={changeRouting} />
              ) : (
                <span className="fixed-model">Model: gpt-5-mini</span>
              )}
              <button type="submit" className="ask-submit"
                disabled={loading || (mode === "agents" && routingBusy) || question.trim().length === 0}>
                {loading ? "Asking…" : "Ask"}
              </button>
            </div>
          </form>

          {mode === "agents" && <p className="router-notice">
            {routing?.editable
              ? "Shared demo control: router changes affect all agent users and can take up to 5 min. AI Gateway stays on gpt-5-mini."
              : "Agents use Model Router. AI Gateway uses the fixed gpt-5-mini deployment."}
          </p>}
          {mode === "agents" && !!routing?.model_subset?.length && (
            <p className="router-subset">Router models: {routing.model_subset.join(" / ")}</p>
          )}
          {mode === "agents" && routingError && (
            <div className="router-load-error" role="alert">
              <span>Routing settings unavailable: {routingError}</span>
              <button type="button" onClick={() => setRoutingRefresh((value) => value + 1)}>
                Retry routing settings
              </button>
            </div>
          )}
          {mode === "agents" && routingMessage && (
            <p className="router-feedback" role="status">{routingMessage}</p>
          )}
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
