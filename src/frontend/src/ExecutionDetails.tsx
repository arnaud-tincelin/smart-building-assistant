import type { ModelExecution } from "./api";

function tokenCount(value: number | null | undefined): string {
  return value == null ? "Not reported" : value.toLocaleString("en-US");
}

export function ExecutionDetails({ execution, expanded, onToggle }: {
  execution?: ModelExecution | null;
  expanded?: boolean;
  onToggle?: (expanded: boolean) => void;
}) {
  if (!execution) {
    return <p className="execution-unavailable">Model details were not reported for this answer.</p>;
  }

  return (
    <section className="model-execution" aria-label="Model execution">
      <div className="execution-heading">
        <div>
          <p className="eyebrow">Reported response model</p>
          <h3>{execution.selected_model || "Model not disclosed"}</h3>
        </div>
        <div className="execution-badges">
          <span>{execution.mode === "gateway" ? "AI Gateway" : "Agents"}</span>
          <span className="routing-mode" title={execution.mode === "gateway"
            ? "Direct model deployment; Model Router is not used"
            : "Shared router configuration at request start"}>
            {execution.mode === "gateway" ? "Fixed model"
              : execution.routing_mode || "Router mode unavailable"}
          </span>
        </div>
      </div>
      {!execution.selected_model && (
        <p className="execution-unavailable">
          The service did not identify the underlying model. A deployment name is not model attribution.
        </p>
      )}
      <details className="routing-details" open={expanded}
        onToggle={(event) => onToggle?.(event.currentTarget.open)}>
        <summary>Show more details</summary>
        <dl className="execution-metrics">
          <div>
            <dt>{execution.mode === "gateway" ? "Gateway latency" : "Agent latency"}</dt>
            <dd>{(execution.latency_ms / 1000).toFixed(2)} s</dd>
          </div>
          <div>
            <dt>Response tokens</dt>
            <dd>{tokenCount(execution.usage?.total_tokens)}</dd>
          </div>
          <div>
            <dt>Input tokens</dt>
            <dd>{tokenCount(execution.usage?.input_tokens)}</dd>
          </div>
          <div>
            <dt>Output tokens</dt>
            <dd>{tokenCount(execution.usage?.output_tokens)}</dd>
          </div>
          <div>
            <dt>Reasoning tokens</dt>
            <dd>{tokenCount(execution.usage?.reasoning_tokens)}</dd>
          </div>
          <div>
            <dt>Cached input tokens</dt>
            <dd>{tokenCount(execution.usage?.cached_tokens)}</dd>
          </div>
          <div>
            <dt>Cache write tokens</dt>
            <dd>{tokenCount(execution.usage?.cache_write_tokens)}</dd>
          </div>
          <div>
            <dt>Requested deployment</dt>
            <dd>{execution.requested_model}</dd>
          </div>
          <div className="execution-metric-wide">
            <dt>Response ID</dt>
            <dd><code>{execution.response_id || "Not reported"}</code></dd>
          </div>
          <div className="execution-metric-wide">
            <dt>Raw reported model</dt>
            <dd>{execution.reported_model || "Not reported"}</dd>
          </div>
          <div className="execution-metric-wide">
            <dt>Reported tools</dt>
            <dd>{execution.tools_used.length ? execution.tools_used.join(", ") : "None reported"}</dd>
          </div>
        </dl>
        <p className="routing-explanation">{execution.routing_explanation}</p>
      </details>
    </section>
  );
}
