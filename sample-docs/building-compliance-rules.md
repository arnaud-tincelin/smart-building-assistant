# Contoso Energy building compliance rules

*Fictional compliance policy for the BuildingAssist demo. Foundry IQ is the
authoritative source for these stable rules; current measurements must come from the
building operations MCP server.*

## How to evaluate compliance

Use the rule whose metric, scope, building, and operating state match the live value.
Minimum and maximum boundaries are inclusive. A value is non-compliant only when it is
strictly below a minimum or strictly above a maximum. Report the live `as_of` timestamp.
Never substitute a rule for a different metric or infer a threshold for a context-only
field. If a required rule, unit, scope, operating state, or live value is missing, the
compliance result is unknown.

## Occupied-zone environmental limits

These limits apply to every zone when its building `operating_status` is `occupied` or
`reduced-hours` and the zone `occupancy_percent` is greater than zero.

| Live zone metric | Compliant range | Unit | Purpose |
|---|---:|---|---|
| `temperature_c` | 20-25 inclusive | degrees C | Occupied-zone thermal comfort |
| `co2_ppm` | 0-1000 inclusive | ppm | Indoor air quality |
| `relative_humidity_percent` | 30-60 inclusive | percent RH | Occupied-zone comfort and moisture control |
| `occupancy_percent` | 0-100 inclusive | percent | Sensor data-quality range |

The `setpoint_c` metric uses the building-specific setpoint limits below rather than
the occupied-zone temperature range.

## Building telemetry limits

| Building | `current_power_kw` maximum | `energy_today_kwh` maximum | `energy_this_week_kwh` maximum | `renewable_share_percent` minimum |
|---|---:|---:|---:|---:|
| `paris-hq` | 200 kW | 1500 kWh | 6500 kWh | 35 percent |
| `seattle-lab` | 280 kW | 2100 kWh | 9500 kWh | 65 percent |
| `munich-ops` | 160 kW | 1200 kWh | 5600 kWh | 45 percent |

For every building, `indoor_temperature_c` must be 20-25 degrees C inclusive and
`occupancy_percent` must be 0-100 percent inclusive. The `hvac_setpoint_c` metric uses
the building-specific setpoint limits below.

`outdoor_temperature_c` is context-only and has no compliance threshold. Do not report
it as compliant or non-compliant.

## Building-specific HVAC setpoint limits

These limits apply to both building `hvac_setpoint_c` and zone `setpoint_c`.

| Building | Compliant range | Unit |
|---|---:|---|
| `paris-hq` | 20-26 inclusive | degrees C |
| `seattle-lab` | 19-25 inclusive | degrees C |
| `munich-ops` | 18-25 inclusive | degrees C |

## Expected demonstration result

With the sample live data dated 2026-08-27, Paris Floor 3 exceeds the occupied-zone
maximum for `temperature_c` and `co2_ppm`. This section describes the expected demo
scenario only; the agent must still retrieve current values from the operations MCP
server and calculate the result instead of treating this statement as live telemetry.