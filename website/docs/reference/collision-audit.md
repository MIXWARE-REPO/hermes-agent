---
sidebar_position: 9
title: "Collision Audit"
description: "First-pass desduplication map for overlapping skills and helpers"
---

# Collision Audit

This document records first-pass collision handling for skills that overlap in intent, input, output, or backend.

Rule: one user intent should resolve to one canonical skill. Everything else should become a service, helper, alias, or preset.

## Collision families

| Family | Canonical skill | Collisions / helpers | Decision |
|---|---|---|---|
| Preliminary analysis reports | `gridcode-preliminary-analysis-report` | `gridcode-preliminary-report-a4-lite` | Keep canonical; lite becomes preset/alias |
| Grid Code PDF documents | `gridcodear-documentos` | `pdf-builder`, `nano-pdf`, `pdf-overlay-hotfix` | Keep `gridcodear-documentos` canonical; `pdf-builder` is now generic/non-Grid-Code |
| Remote OCPP analysis | `gridcode-aggregated-behavior-remote-analysis` | `ocpp-log-unpack-7d-analysis` | Keep canonical; unpacking becomes helper |
| Webasto endpoint operations | `webasto-full-production-run` / `webasto-unite-log-analysis-production-report` | `webasto-set-ocpp-endpoint`, `webasto-verify-ocpp-persistence` | Keep user-facing flows canonical; endpoint ops stay backend helpers |
| LinkedIn workflow | `linkedin-li-preset-v1` | `linkedin-message-standard-v1`, `linkedin-posting-random-window-v1`, `linkedin-trend-intensity-3w` | Keep preset canonical; the others become service helpers |
| Google Workspace / email boundary | `google-workspace` | `mail-cli`, `mail-imap-only-lock` | Keep Google Workspace for Google services; mail stays on the dedicated mail stack |
| GitHub repo workflow | `github-pr-workflow` | `github-code-review`, `github-issues`, `github-repo-management`, `github-auth` | Keep separate frontend workflows; auth is backend plumbing |
| Presentation output | `powerpoint` | none yet | Canonical output factory; keep PPTX as the standard presentation contract |
| Meeting capture | `google-meet-capture` | future transcript helpers | Keep capture as a service helper until it becomes a user-facing primary skill |

## Open items

- Decide whether `github-auth` should stay exposed at all or be fully absorbed into GitHub workflows.
- Decide whether `google-meet-capture` should evolve into a user-facing meeting transcript skill.
- Decide whether a dedicated `skill-blacksmith` should be exposed or remain an internal factory.

## Resolved partial-family decisions

Audit result for this pass: the families below were reviewed and their members were promoted or kept as helpers instead of remaining pending.

| Family | Current members | Recommended route |
|---|---|---|
| Auth / secrets | `1password` | Backend-only support; keep hidden as internal plumbing |
| Mail / inbox | `agentmail`, `mail-cli`, `mail-imap-only-lock`, `send-email-with-signature` | Keep `mail-cli` for personal mail; `agentmail` is a separate canonical inbox route |
| Blockchain | `base`, `solana` | Keep both as separate canonical routes; do not merge them |
| BCI / neurofeedback | `neuroskill-bci` | Canonical frontend route |
| Migration | `openclaw-migration` | Canonical one-shot migration route |
| Smart home | `openhue` | Canonical frontend route |
| Security research | `oss-forensics`, `sherlock` | Canonical frontend routes with standardized outputs |
| Runtime meta | `hermes-agent`, `godmode` | Canonical frontend routes for agent support and red-teaming intent |
