---
description: Create a well-structured GitHub issue following product and engineering best practices
agent: agent
argument-hint: Describe the feature, bug, enhancement, technical debt, or task to create as a GitHub issue
---

# Goal

Create a GitHub issue from the provided request.

User request:

${input:request:Describe the requested feature, bug, enhancement, or work item}

# Instructions

Act as an experienced Product Manager and Engineering Lead.

Analyze the request and produce a GitHub issue that is:

- Clear and unambiguous
- Actionable by an engineering team
- Testable through measurable acceptance criteria
- Free from implementation assumptions unless explicitly provided
- Suitable for Agile delivery

If information is missing:

- Explicitly list assumptions
- Highlight open questions
- Do not invent business requirements

# Output Format

## Title

Create a concise title using one of these prefixes:

- [Feature]
- [Bug]
- [Enhancement]
- [Technical Debt]
- [Spike]

## Summary

Provide a short description of the problem or opportunity.

## Business Value

Explain:

- Why this work matters
- Who benefits
- Expected outcome

## Problem Statement

Describe:

- Current behavior or situation
- Pain points
- Impact

## Scope

### In Scope

List what must be delivered.

### Out of Scope

List what is explicitly excluded.

## User Story

When applicable use:

As a <user persona>,
I want <capability>,
So that <expected outcome>.

## Requirements

Provide numbered functional requirements.

Example:

1. The system shall ...
2. The system shall ...
3. The system shall ...

## Acceptance Criteria

Use Gherkin syntax.

Example:

### AC1

Given <context>
When <action>
Then <expected result>

### AC2

Given <context>
When <action>
Then <expected result>

Requirements:

- Acceptance criteria must be independently testable
- Avoid vague wording such as "fast", "easy", "good"
- Use measurable outcomes whenever possible

## Non-Functional Requirements

If applicable include:

- Performance
- Security
- Accessibility
- Reliability
- Compliance
- Observability

## Dependencies

List:

- Upstream dependencies
- External services
- Teams involved

## Risks

Identify potential delivery, business, or technical risks.

## Open Questions

List missing information that requires clarification.

## Definition of Done

The issue is complete when:

- All acceptance criteria pass
- Relevant tests are added or updated
- Documentation is updated if required
- Monitoring/logging requirements are implemented if applicable
- Code review is completed
