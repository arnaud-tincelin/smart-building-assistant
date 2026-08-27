# BuildingAssist backend

FastAPI service for the *"A Developer's Day on the Microsoft Agentic Platform"*
demo. It exposes:

- `POST /ask`: invokes the provisioned Microsoft Foundry prompt agent by reference.
	The agent uses Model Router, Foundry IQ, and current simulated telemetry.
- `/mcp/`: a stateless Streamable HTTP MCP server with building snapshots, alerts,
	work-order creation, and bounded temporary HVAC actions.

The operations dataset is fictional and resets when the process restarts. HVAC
changes require confirmation and enforce per-site policy limits.

See the repository [README](../../README.md) for the full demo run-sheet.
