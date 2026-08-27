# Contoso Energy building operations policy

*Fictional policy for the BuildingAssist demo. It governs simulated actions only.*

## Data and action boundaries

Foundry IQ contains stable facts and approved operating guidance. Current conditions
must come from the building operations MCP server. Every MCP result is simulated and
must be described as such to the user.

The demo agent can perform these actions:

1. Create a maintenance work order with a building, title, reason, and priority.
2. Apply a temporary HVAC setpoint to a named zone for a bounded duration.

Creating a work order is non-destructive and can happen when the user directly asks
for one. An HVAC adjustment changes simulated operational state and requires explicit
confirmation after the agent repeats the building, zone, requested temperature,
duration, and reason.

## HVAC limits

| Building | Allowed setpoint | Maximum duration | Additional rule |
|---|---:|---:|---|
| `paris-hq` | 20-26 C | 240 minutes | Floor 3 and Floor 5 may be adjusted. |
| `seattle-lab` | 19-25 C | 180 minutes | Do not relax prototype-lab ventilation requirements. |
| `munich-ops` | 18-25 C | 240 minutes | Do not use the `dispatch` zone for demand response. |

The MCP server enforces numeric temperature and duration limits. BuildingAssist must
not claim an action succeeded until the tool returns an `applied` or `created` status.
If a tool rejects an action, explain the policy limit and offer a compliant alternative.

## Good demo actions

- Investigate an efficiency alert, compare it with building-specific guidance, and
  create a high-priority inspection work order.
- Review peak demand and temporarily relax an eligible office-zone cooling setpoint.
- Identify delayed meter data and explain when it is expected behaviour for that site.

Useful future production tools would include acknowledging alerts, scheduling battery
charging, enrolling an eligible zone in a demand-response event, and checking work-order
status. Those operations would require authenticated MCP, durable state, audit logging,
role-based authorization, and approval policies before controlling real equipment.