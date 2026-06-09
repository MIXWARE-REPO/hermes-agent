---
sidebar_position: 7
title: "Los 40 Principales"
description: "Working map of the 40 principal Hermes capabilities across frontend, services, and backend"
---

# Los 40 Principales

This is the working governance map for the 40 principal capabilities.

It is intentionally elastic:
- Frontend = user-facing outcome or action
- Services = reusable enablers consumed by frontend skills
- Backend = hidden operational machinery

A skill can change layer over time, but it should keep one primary layer at any moment.

## Core table

| # | Skill | Layer | Visibility | Role | Status |
|---|---|---|---|---|---|
| 1 | `ticket-handler` | Frontend | User-facing | Support ticket actions and responses | Canonical |
| 2 | `calendar-meet-host-gridcode` | Frontend | User-facing | Create and manage meetings | Canonical |
| 3 | `send-email-with-signature` | Frontend | User-facing | Send signed email through the mail rail | Canonical |
| 4 | `dario-executive-mail-review` | Frontend | User-facing | Executive mail triage and review | Canonical |
| 5 | `gridcode-technical-service-report-pdf` | Frontend | User-facing | Technical service report generation | Canonical |
| 6 | `gridcode-preliminary-analysis-report` | Frontend | User-facing | Preliminary analysis report generation | Canonical |
| 7 | `gridcode-preliminary-report-a4-lite` | Frontend | User-facing | Lightweight preset for preliminary analysis | Alias / preset |
| 8 | `onsite-mobile-pdf-form-design` | Frontend | User-facing | Editable onsite form generation | Canonical |
| 9 | `gridcode-aggregated-behavior-remote-analysis` | Frontend | User-facing | Remote technical analysis workflow | Canonical |
| 10 | `webasto-unite-log-analysis-production-report` | Frontend | User-facing | Webasto log analysis report workflow | Canonical |
| 11 | `webasto-full-production-run` | Frontend | User-facing | Full production flow for Webasto | Canonical |
| 12 | `nuba-full-production-run` | Frontend | User-facing | Full production NUBA workflow | Canonical |
| 13 | `linkedin-li-preset-v1` | Frontend | User-facing | LinkedIn high-level workflow preset | Canonical |
| 14 | `youtube-content` | Frontend | User-facing | YouTube transcript and content transformation | Canonical |
| 15 | `mindcode-create-discussion` | Frontend | User-facing | Create a MindCode discussion | Canonical |
| 16 | `google-meet-capture` | Services | Hidden | Meeting subtitle and transcript capture | Helper |
| 17 | `github-pr-workflow` | Frontend | User-facing | Full pull request lifecycle | Canonical |
| 18 | `github-code-review` | Frontend | User-facing | Code review workflow | Canonical |
| 19 | `github-issues` | Frontend | User-facing | Issue triage and management | Canonical |
| 20 | `github-repo-management` | Frontend | User-facing | Repository lifecycle management | Canonical |
| 21 | `dogfood` | Services | Hidden | Absorbed QA utility on top of Handler Web | Helper |
| 22 | `powerpoint` | Frontend | User-facing | Presentation factory | Canonical |
| 23 | `charger-ocpp-certification-rigid-v1` | Frontend | User-facing | OCPP interoperability certificate generation | Canonical |
| 24 | `colonial-vpn-charger-access` | Backend | Hidden | Colonial VPN access and charger reachability validation | Canonical |
| 25 | `colonial-vpn-rigid-runner` | Backend | Hidden | OpenVPN connection and session validation | Helper |
| 26 | `colonial-vpn-bridge-rigid` | Backend | Hidden | VPN bridge to enable Webasto analysis | Helper |
| 27 | `webasto-set-ocpp-endpoint` | Backend | Hidden | Set OCPP endpoint via strict runner | Helper |
| 28 | `telephony` | Frontend | User-facing | SMS / calls / telephony actions | Canonical |
| 29 | `google-workspace` | Services | Hidden | Workspace API bridge for Drive / Calendar / Docs / Sheets | Canonical |
| 30 | `mail-imap-only-lock` | Backend | Hidden | IMAP / SMTP transport and locking | Canonical |
| 31 | `gridcodear-documentos` | Services | Hidden | Canonical Grid Code document factory for technical, administrative, and commercial PDFs | Canonical |
| 32 | `nano-pdf` | Services | Hidden | PDF micro-edits and lightweight transforms | Helper |
| 33 | `pdf-overlay-hotfix` | Services | Hidden | Quick PDF correction and overlay operations | Helper |
| 34 | `ocpp-log-unpack-7d-analysis` | Services | Hidden | OCPP log unpacking helper | Helper |
| 35 | `webasto-set-ocpp-endpoint` | Backend | Hidden | Backend procedure tied to a client-requested OCPP endpoint change | Helper |
| 36 | `webasto-verify-ocpp-persistence` | Backend | Hidden | Backend procedure that confirms the endpoint change persisted | Helper |
| 37 | `nuba-login-check` | Backend | Hidden | Backend access check that supports client-facing NUBA workflows | Helper |
| 38 | `linkedin-message-standard-v1` | Services | Hidden | LinkedIn message composition helper | Helper |
| 39 | `linkedin-posting-random-window-v1` | Services | Hidden | LinkedIn posting window orchestration | Helper |
| 40 | `linkedin-trend-intensity-3w` | Services | Hidden | LinkedIn trend analysis helper | Helper |

## Output contracts

These are the default output types for the principal capability families:

Note: Colonial VPN entries are treated as one single connectivity family; the visible rows are helper/bridge variants over the same unique connection.

- Reports and technical analyses -> HTML + PDF
- Onsite / field workflows -> editable PDF
- Presentations -> PPTX
- Video workflows -> MP4
- Structured operational actions -> platform-native result + audit trail

## Immediate expansion candidates

These are not part of the first 40, but they are next in line for profiling and/or canonicalization:

- `skill-observability`
- `skill-blacksmith`
- `contact-enrichment`
- `google-workspace` submodes that need tighter contracts
- `whisper` / meeting transcript-related flows if they become visible as a user-facing capability
- any helper that repeatedly appears in the backend and deserves promotion or aliasing

## Governance rule

When a skill is added, promoted, merged, or demoted, update this table first.
The table is the strategic view; the individual SKILL.md files are the execution view.
For broader coverage of the repository, use the [Skills Profile Index](/docs/reference/skills-profile-index), [Collision Audit](/docs/reference/collision-audit), and [Partial Skills Audit](/docs/reference/partials-audit).
