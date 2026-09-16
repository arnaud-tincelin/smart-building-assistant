import { useState } from "react";
import type { ExecutionInfo } from "./api";

function formatLatency(ms?: number | null): string | null {
  if (typeof ms !== "number" || Number.isNaN(ms)) return null;
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatCount(value?: number | null): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value.toLocaleString("en-US");
}

function toolLabel(name: string): string {
  const separator = name.indexOf("_");
  return separator >= 0 ? name.slice(separator + 1) : name;
}

/**
 * Displays the model that produced a single agent reply, plus its collapsible
 * routing/usage metrics. Each reply carries its own `execution` payload, so
 * this component never needs to know about later replies or router changes.
 */
export function ExecutionDetails({ execution }: { execution?: ExecutionInfo | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!execution || !execution.selected_model) {
    return (
      <div className="model-execution model-execution--unavailable">
        <p className="eyebrow">Model router</p>
        <p className="model-unavailable">Model attribution is not disclosed for this reply.</p>
      </div>
    );
  }

  const { selected_model, routing_mode, latency_ms, response_id, routing_explanation, tools_used, usage } =
    execution;
  const latency = formatLatency(latency_ms);
  const totalTokens = formatCount(usage?.total_tokens);

  return (
    <div className="model-execution">
      <div className="model-execution__header">
        <div>
          <p className="eyebrow">Model router</p>
          <h3>{selected_model}</h3>
        </div>
        {routing_mode && <span className="routing-mode">{routing_mode}</span>}
      </div>
      <button
        type="button"
        className="routing-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        Show more details
      </button>
      {expanded && (
        <div className="routing-details">
          <div className="routing-metrics">
            <div className="routing-metric">
              <span className="routing-metric__label">Agent latency</span>
              <span className="routing-metric__value">{latency ?? "Not reported"}</span>
            </div>
            <div className="routing-metric">
              <span className="routing-metric__label">Response tokens</span>
              <span className="routing-metric__value">{totalTokens ?? "Not reported"}</span>
            </div>
            <div className="routing-metric">
              <span className="routing-metric__label">Response ID</span>
              <span className="routing-metric__value">{response_id ?? "Not reported"}</span>
            </div>
          </div>
          {routing_explanation && <p className="routing-explanation">{routing_explanation}</p>}
          {tools_used && tools_used.length > 0 && (
            <div className="routing-tools">
              <span className="routing-metric__label">Tools observed</span>
              <ul>
                {tools_used.map((tool) => (
                  <li key={tool}>
                    <code>{toolLabel(tool)}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
