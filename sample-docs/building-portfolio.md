# Contoso Energy building portfolio

*Fictional reference data for the BuildingAssist demo. These are stable portfolio
facts for Foundry IQ grounding, not live telemetry.*

## Contoso Energy HQ

- Operations ID: `paris-hq`
- Location: Paris, France
- Time zone: Europe/Paris
- Gross floor area: 18,400 square metres across seven occupied floors
- Normal hours: 07:00-20:00 Monday-Friday
- Primary systems: variable-air-volume HVAC, district cooling, LED lighting, and
  rooftop solar
- Metering: whole-building electricity plus floor-level HVAC, lighting, and plug
  load submeters at 15-minute intervals
- Specificity: Floor 3 combines open-plan offices and meeting rooms. It has the
  portfolio's highest afternoon cooling sensitivity and a normal weekly range of
  1,050-1,300 kWh.
- Sustainability target: reduce peak electrical demand by 12% from the 2025
  baseline while maintaining occupied-zone comfort.

MCP zone IDs used by the operations platform are `floor-3` and `floor-5`.

## Contoso Innovation Center

- Operations ID: `seattle-lab`
- Location: Seattle, United States
- Time zone: America/Los_Angeles
- Gross floor area: 12,600 square metres
- Normal hours: offices 07:00-19:00; prototype lab operates continuously
- Primary systems: air-source heat pumps, dedicated outside-air system, lab
  extraction, battery storage, and rooftop solar
- Metering: five-minute electrical telemetry for laboratory equipment and
  15-minute telemetry for office loads
- Specificity: the prototype lab has a high and comparatively inflexible base
  load. Office HVAC and battery charging are the preferred demand-response levers.
- Sustainability target: keep at least 65% of annual electricity matched by
  renewable generation and shift battery charging outside 16:00-20:00.

MCP zone IDs are `prototype-lab` and `office-east`.

## Contoso Operations Campus

- Operations ID: `munich-ops`
- Location: Munich, Germany
- Time zone: Europe/Berlin
- Gross floor area: 21,900 square metres across a dispatch centre and two warehouses
- Normal hours: dispatch operates continuously; warehouses run 06:00-18:00
- Primary systems: condensing boilers, packaged cooling, destratification fans,
  warehouse lighting controls, and electric-vehicle charging
- Metering: 15-minute electricity and gas readings; warehouse meters can arrive
  one collection interval late without indicating a fault
- Specificity: the dispatch centre is comfort-critical. Warehouse temperature and
  EV charging are flexible, but dispatch setpoints must not be used for demand response.
- Sustainability target: reduce combined gas and electricity emissions by 20% from
  the 2024 baseline.

MCP zone IDs are `dispatch` and `warehouse-a`.

## How to use this knowledge

Use this source for building identity, operating characteristics, meter semantics,
normal schedules, and sustainability targets. Use the building operations MCP tools
for current power, energy, occupancy, temperatures, alerts, and action results.