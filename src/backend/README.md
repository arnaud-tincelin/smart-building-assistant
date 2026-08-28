# BuildingAssist backend

FastAPI service for the *"A Developer's Day on the Microsoft Agentic Platform"*
demo. It exposes:

- `POST /ask`: invokes the provisioned Microsoft Foundry prompt agent by reference.
	The agent uses Model Router, Foundry IQ, and current simulated telemetry.
- `POST /security/access-requests`: validates a simulated employee badge or mobile
	credential at the Paris HQ lobby.
- `POST /security/visitors/check-in`: registers a simulated visitor and issues a
	temporary lobby pass.
- `/operations/*`: ordinary REST operations for building snapshots, alerts,
	work-order creation, and bounded temporary HVAC actions. APIM imports these
	operations and exposes selected operations as MCP tools.

The operations dataset is fictional and resets when the process restarts. HVAC
changes require confirmation and enforce per-site policy limits. The two security
endpoints intentionally share a broken audit-event adapter for the SRE Agent demo;
they return a correlated HTTP 500 until the coding-agent repair is deployed.

See the repository [README](../../README.md) for the full demo run-sheet.
