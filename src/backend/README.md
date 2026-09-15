# BuildingAssist backend

FastAPI service for the *"A Developer's Day on the Microsoft Agentic Platform"*
demo. It exposes:

- `POST /ask`: accepts `{"question": "...", "mode": "agents"}` to invoke the single
  provisioned Microsoft Foundry prompt agent by reference. The agent uses Model
  Router (restricted to gpt-4o-mini and gpt-5.6-sol), Foundry IQ, and current
  simulated telemetry. Omitting `mode` preserves this default.
- `POST /ask` with `"mode": "gateway"`: calls the APIM AI Gateway model endpoint
  directly using **gpt-5-mini**, with a bounded read-only MCP tool loop. This path
  does not query Model Router or use its mode setting, Foundry IQ, or action tools.
  It never silently falls back to the agent. Policy rejections and
  rate limits remain explicit HTTP errors.
- `GET /model-router/mode`: reads the current shared deployment setting.
- `PUT /model-router/mode`: accepts `{"mode": "cost"}`, `"balanced"`, or `"quality"`.
  It returns HTTP 403 unless `BUILDINGASSIST_ENABLE_ROUTER_CONTROL=true`. Editing
  affects all agent callers and requires deployment-scoped ARM read/write permission.
  The existing two-model subset is preserved; the API does not allow editing it.
  AI Gateway's fixed gpt-5-mini model is unaffected.
  Allow up to five minutes for model-service propagation.
- `POST /security/access-requests`: validates a simulated employee badge or mobile
	credential at the Paris HQ lobby.
- `POST /security/visitors/check-in`: registers a simulated visitor and issues a
	temporary lobby pass.
- `/operations/*`: ordinary REST operations for building snapshots, alerts,
	work-order creation, and bounded temporary HVAC actions. APIM imports these
	operations and exposes selected operations as MCP tools.

Answers include optional `execution` metadata: request mode, requested deployment,
reported/selected model, router configuration at request start, elapsed time, response
ID, token counts, and reported tools. The configured deployment is not a substitute
for model attribution. Missing counts remain `null`, not zero. Gateway counts are
summed across all model calls only when every call reports the measurement; its
model identity comes from the final response. No per-request router reasoning is
invented. For fixed gateway calls, `routing_mode` is `null` because Model Router
does not apply, and the response identifies the configured gpt-5-mini deployment
separately from the reported model/version.

See [`.env.example`](.env.example) for gateway and router settings. Gateway keys stay
on the backend. The local mock-agent flag does not mock the gateway.

Client-side agent tracing uses sampling-safe OpenTelemetry spans, propagates W3C
trace context without baggage, and exports model/token metadata without message
content. It deliberately avoids the Azure AI Projects Responses instrumentor's
`NonRecordingSpan.attributes` failure. Foundry's server-side tracing remains enabled.
Model rate limits remain HTTP 429 responses with the upstream `Retry-After` hint,
rather than being reported as backend HTTP 502 failures.

The operations dataset is fictional and resets when the process restarts. HVAC
changes require confirmation and enforce per-site policy limits. The two security
endpoints intentionally share a broken audit-event adapter for the SRE Agent demo;
they return a correlated HTTP 500 until the coding-agent repair is deployed.

See the repository [README](../../README.md) for the full demo run-sheet.
