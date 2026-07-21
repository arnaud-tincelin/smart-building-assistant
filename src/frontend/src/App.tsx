import { FormEvent, useState } from "react";
import { ask, type AskResponse } from "./api";

const SAMPLE_QUESTION = "How much energy did Floor 3 use this week?";

export function App() {
  const [question, setQuestion] = useState(SAMPLE_QUESTION);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <main className="app">
      <header>
        <h1>BuildingAssist</h1>
        <p className="subtitle">Contoso Energy · Smart Building assistant</p>
      </header>

      <form onSubmit={onSubmit} className="ask-form">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={SAMPLE_QUESTION}
          aria-label="Energy question"
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
                {result.citations.map((c, i) => (
                  <li key={i}>
                    {c.url ? (
                      <a href={c.url} target="_blank" rel="noreferrer">
                        {c.title || c.url}
                      </a>
                    ) : (
                      <span>{c.title}</span>
                    )}
                    {c.snippet && <p className="snippet">{c.snippet}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
