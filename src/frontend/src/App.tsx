import { FormEvent, useState } from "react";
import {
  ApiError,
  ask,
  checkInVisitor,
  requestAccess,
  type AskResponse,
  type SecurityOperationResponse,
} from "./api";

const SAMPLE_QUESTION =
  "Why is Floor 3 energy-sensitive, and what is happening there now?";

type View = "assistant" | "security";
type AccessMethod = "badge" | "mobile";

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
  const [question, setQuestion] = useState(SAMPLE_QUESTION);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accessMethod, setAccessMethod] = useState<AccessMethod>("badge");
  const [accessState, setAccessState] = useState<OperationState>(EMPTY_OPERATION);
  const [visitorState, setVisitorState] = useState<OperationState>(EMPTY_OPERATION);
  const credentialId = accessMethod === "badge" ? "BDG-1042" : "MOB-2048";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await ask(question));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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
          <form onSubmit={onSubmit} className="ask-form">
            <input
              type="text"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={SAMPLE_QUESTION}
              aria-label="Building question"
            />
            <button type="submit" disabled={loading || question.trim().length === 0}>
              {loading ? "Asking…" : "Ask"}
            </button>
          </form>

          {error && <div className="error">{error}</div>}

          {result && (
            <section className="answer">
              <h2>Answer</h2>
              <p>{result.answer}</p>

              {result.citations.length > 0 && (
                <div className="citations">
                  <h3>Sources</h3>
                  <ul>
                    {result.citations.map((citation, index) => (
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
            </section>
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
