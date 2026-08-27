# Demo Plan — "A Developer's Day on the Microsoft Agentic Platform"

**Customer:** Contoso Energy — ICT systems integrator & managed-services provider
**Audience / persona:** Contoso Energy developers, tech leads, platform & DevOps engineers (technical decision-makers)
**Duration:** 60 minutes (live product demo)
**Owner:** Arnaud Tincelin — Solution Engineer, Microsoft France
**Status:** Draft plan — to build & rehearse

---

## 1. Objective & key message

Show what a developer's day feels like when the platform has an **agent at every stage of the software lifecycle** — and that all those agents live on **one Microsoft platform, in the customer's own tenant**.

> **Key message:** Microsoft gives developers agents at every stage — GitHub Copilot to **write**, Azure AI Foundry to **reason**, Azure SRE Agent to **operate**, and the Copilot coding agent to **fix** — with the developer in control at the decisions that matter.

**Design principles**
- **The platform is the star, not the app.** The demo app stays deliberately thin — it only exists to give the agents something to act on.
- **Three equal pillars.** GitHub Copilot, Azure AI Foundry, and Azure SRE Agent get equal billing. The SRE moment is one capability among peers, **not** a climax.
- **Copilot bookends the hour** (VSCode at the start, the coding agent at the end), so the operate stage hands the loop back to the build stage.
- **Human-in-the-loop stays visible** — the developer makes exactly one decision on the critical path (the merge).

**The three questions the audience is really asking** (map to the three pillars):
| Question | Pillar |
|---|---|
| How fast can I build? | 🟦 GitHub Copilot |
| How much control do I keep? | 🟩 Azure AI Foundry |
| How little toil to run it? | 🟧 Azure SRE Agent |

---

## 2. The demo app (a thin backdrop — do not over-invest)

**BuildingAssist** — a minimal Smart Building assistant. A tenant/facility user asks one simple question — *"How much energy did Floor 3 use this week?"* — and a **Foundry agent** answers.

- One endpoint, one agent, no depth.
- Everything interesting happens *around* the app (the agents at each stage), not *inside* it.
- On-brand for Contoso Energy (buildings / energy / IoT) without pulling focus.

---

## 3. Architecture & components to build

```
 🟦 WRITE            🟩 REASON            🟧 OPERATE               🟦 FIX
 GitHub Copilot  →  Foundry Agent  →     Azure       →         SRE Agent      →   Copilot coding agent
   (VSCode)       (Router + IQ + MCP)  (Container Apps)         (RCA → GitHub issue)   (PR → HITL merge)
        └──────────── every model call through APIM AI Gateway ────────────┘
        └──────────────── every agent governed by Agent 365 ───────────────┘
```

| Component | Role in the demo |
|---|---|
| **GitHub repo + CI/CD** | Source of truth; pipeline deploys to Azure; target for the SRE Agent's issue and the coding agent's PR |
| **GitHub Copilot (VSCode)** | Writes the app feature (agent mode) |
| **Microsoft Foundry agent** | The reasoning behind the app; tenant-resident, tool-using, model-flexible |
| **Model Router** | Selects an eligible model per request behind one Balanced deployment |
| **Foundry IQ** | Grounds the agent in a reusable Azure AI Search Knowledge Base with citations |
| **Building operations MCP** | Supplies simulated live telemetry and approval-gated actions |
| **APIM AI Gateway** *(optional)* | Governs model calls — token limits, load-balancing, retries, managed identity; also the regression lever |
| **Azure Container Apps** | Hosts BuildingAssist |
| **Azure SRE Agent** | Watches the resources, root-causes the regression, opens a GitHub issue |
| **Copilot coding agent** | Takes the issue, opens a fix PR autonomously |
| **Agent 365** | Governance-plane talking point at the close (no build required) |

---

## 4. The staged regression (failure mechanic)

Keep it **routine, not dramatic** — "the kind of thing that normally eats an afternoon."

- **Trigger:** a recent commit quietly changes a config/timeout on the model calls (or references a wrong/expired model deployment). After deploy, BuildingAssist starts erroring / slowing.
- **What the SRE Agent does:** detects the regression, correlates it to the recent deploy, reads logs across app + Foundry + APIM, writes a plain-language root cause, and opens a GitHub issue with the diagnosis.
- **The fix:** the Copilot coding agent adds the timeout/retry (or corrects the config) in a PR.
- ⚠️ **Rehearse until reproducible**, and record a fallback video — a broken live regression is the #1 demo risk.

---

## 5. One-hour run sheet

| Time | Beat | Screen | Pillar |
|---|---|---|---|
| 0:00–0:05 | **Open** — agents at every stage | Slide | — |
| 0:05–0:17 | **Write** — code the feature | VSCode + GitHub Copilot | 🟦 Copilot |
| 0:17–0:31 | **Reason** — Model Router + Foundry IQ + MCP tools | Azure Portal → Foundry | 🟩 Foundry |
| 0:31–0:38 | **Operate** — meet the SRE Agent | SRE Agent config | 🟧 SRE Agent |
| 0:38–0:48 | **Diagnose** — a routine regression | App + SRE Agent RCA | 🟧 SRE Agent |
| 0:48–0:57 | **Fix** — coding agent closes the loop | GitHub issue → coding agent → PR → deploy | 🟦 Copilot *(HITL)* |
| 0:57–1:00 | **Close** — one platform, governed | Reveal slide | Agent 365 |

*Balance: Copilot ≈ 22 min (bookends) · Foundry ≈ 14 min · SRE Agent ≈ 17 min.*

---

## 6. Act-by-act detail

### Open — agents at every stage (5 min)
Set the frame: one hour as a developer building one small feature. Nothing about the app is special — that's the point. Show the loop as a ring: **Write → Reason → Operate → Fix → (back to Write)**.

### 🟦 Pillar 1 — Write it · VSCode + GitHub Copilot (12 min)
- **Show:** Copilot agent mode builds the feature — *"add an endpoint that calls our Foundry agent to answer an energy question and return it with sources."* Generates code + test + Dockerfile/Bicep. Review, tweak one thing, run locally.
- **Say:** *"This isn't autocomplete — I delegated a whole task and reviewed the result. That's the pattern for the whole hour."*
- **Why Contoso Energy cares:** delivery velocity on billable work; consistency across a delivery practice; juniors productive on day one.

### 🟩 Pillar 2 — Reason · Azure Portal → Foundry (14 min)
- **Show:** the agent's `model-router` deployment, instructions, Foundry IQ Knowledge Base, and MCP tools. Ask about a building-specific constraint, ask for current telemetry, then create a work order and show the approval checkpoint.
- **Show:** open the Model Router playground and point out the underlying model selected for two prompts of different complexity. In Azure Monitor, split the router deployment metrics by underlying model.
- **Say:** *"Stable facts come from the knowledge base, current state and actions come through MCP, and Model Router chooses an eligible model for each request. None of that orchestration is hard-coded into the UI."*
- **Why Contoso Energy cares:** a platform, not a black box — tenant-resident, model-flexible, resellable to clients as a managed offer.
- **Optional slot-in:** route model calls through APIM AI Gateway for token rate-limits, retries, observability, and managed identity.

### 🟧 Pillar 3 — Operate · Azure SRE Agent (17 min, two beats)
- **Beat A — meet the operator (7 min):** show the SRE Agent config — resources watched (app, Foundry endpoint, APIM), scoped permissions, GitHub integration. *"Same idea as Copilot, but for running the app. Hold that thought."*
- **Beat B — a routine regression (10 min):** trigger the staged regression; the SRE Agent detects it, correlates to the deploy, reads logs, writes a root cause, and opens a GitHub issue. *"It didn't hand me a red dashboard — it handed me a diagnosis and a GitHub issue. That's triage done — one capability among peers."*
- **Why Contoso Energy cares:** the managed-services multiplier — L1/L2 triage before a human is paged; one engineer supervising many more services.

### 🟦 Pillar 1 (return) — Fix it · Copilot coding agent (9 min) — HITL
- **Show:** assign the SRE Agent's issue to the Copilot coding agent → it opens a PR with the fix → **⏸️ you review, approve, merge** → CI/CD redeploys → SRE Agent confirms healthy.
- **Say:** *"The operate agent handed work back to the build agent. The loop closed itself — and I made exactly one decision, the merge."*

### Close — one platform, governed (3 min)
- Reveal the loop as one governed picture (Section 3 diagram).
- Name the two governance planes: **APIM AI Gateway** governs every *model call*; **Agent 365** governs every *agent* — "managed with the same rigour as users, apps, and devices."
- **The line:** *"Other platforms give you an agent for one stage. Microsoft gives developers agents across the whole loop — on one platform, in your tenant, under one governance plane."*
- **CTA:** *"Pick one internal app and let's run this exact loop with your team in a workshop."*

---

## 7. Build prerequisites & setup checklist

- [ ] Thin **BuildingAssist** app in a **GitHub repo** with **CI/CD to Azure Container Apps**
- [ ] One **Foundry agent** using **Model Router**, a **Foundry IQ Knowledge Base**, and the simulated **building operations MCP** server
- [ ] **APIM AI Gateway** in front of the model (also the regression lever)
- [ ] **Azure SRE Agent** on those resources + **GitHub issue integration** enabled
- [ ] A **rehearsed, reproducible regression** + a **recorded fallback**
- [ ] Repo access granted for the **Copilot coding agent**
- [ ] Dry-run the full loop end-to-end at least once before the session

---

## 8. Risks & fallbacks

| Risk | Mitigation |
|---|---|
| Live regression doesn't reproduce | Rehearse to a script; keep a recorded fallback of the SRE Agent RCA + coding-agent PR |
| Coding agent PR takes too long live | Pre-stage a branch; if it stalls, cut to a prepared PR and narrate |
| Foundry/APIM latency during the demo | Warm up the endpoints beforehand; have the playground pre-loaded |
| Audience drifts into deep technical Q&A | Note questions for follow-up; keep the loop moving |
| Time overrun | Cut the APIM deep dive; keep one KB question and one MCP action |

---

## 9. Next steps

- [ ] Assign a builder + timeline for the environment (Section 7)
- [ ] Rehearse the regression until reliable
- [ ] Rehearse the Foundry IQ → MCP read → MCP approval sequence
- [ ] Optional companion assets: slide deck to present, one-page runbook, or an interactive HTML storyboard + seller prep guide
- [ ] Book the follow-up workshop offer as the demo CTA

---

*Adapted from the demo-experience-builder framework for a developer / SRE audience — keeping the human-in-the-loop checkpoint, architecture reveal, Foundry IQ grounding, and Agent 365 governance close; the Fabric/Work/Web business-process layers were intentionally dropped as off-target for this technical audience.*
