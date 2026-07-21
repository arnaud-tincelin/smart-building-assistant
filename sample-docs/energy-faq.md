# Contoso Energy — Building energy FAQ (sample)

*Sample document for the BuildingAssist demo. Used to ground the Foundry agent
via Foundry IQ so answers carry citations.*

## What counts as "energy used by a floor"?

The sum of all submeters assigned to that floor's electrical panel — typically
HVAC, lighting, and plug loads. Shared risers (elevators, base-building systems)
are metered separately and are not attributed to a single floor.

## How fresh is the data?

Submeter readings are collected every 15 minutes and aggregated hourly. Weekly
figures are finalised at 02:00 on Monday for the preceding Mon–Sun window.

## Why might a floor's usage jump week over week?

- Weather: warmer or colder outdoor temperatures change HVAC demand.
- Occupancy: more people on site, longer working hours, events.
- Equipment: new hardware, server rooms, or faulty always-on devices.

## Typical Floor 3 baseline

Floor 3 (open-plan offices) usually runs between 1,050 and 1,300 kWh per week,
with HVAC the largest and most weather-sensitive component.
