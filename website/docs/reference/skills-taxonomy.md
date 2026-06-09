---
sidebar_position: 6
title: "Skills Taxonomy"
description: "Frontend, services, and backend profiling model for Hermes skills"
---

# Skills Taxonomy

Hermes skills are easiest to govern when they are profiled by layer, not just by name or category.

This taxonomy uses three layers:

- Frontend: user-visible capabilities. The user can reasonably ask for them directly because they create an outcome, an artifact, or an action.
- Services: reusable enablers. They help one or more frontend skills finish the job, but they are not the main user-facing promise.
- Backend: hidden infrastructure. The user usually does not ask for these directly; they are operational support for auth, transport, persistence, scheduling, parsing, and integrations.

A skill may depend on multiple layers internally, but it should have one primary layer for governance.

## Layer definitions

### Frontend

A frontend skill is a public capability.
It should be discoverable, describable in user language, and safe to use as an instruction target.

Examples:
- create a meeting
- draft and send an email
- generate a report
- build a PDF
- publish a post
- create a presentation
- capture and summarize a transcript

### Services

A service is a reusable capability that a frontend skill consumes.
It often has a clear technical function, but it is not usually the user's end goal.

Examples:
- HTML to PDF rendering
- OCR extraction
- subtitle capture
- file upload
- document merge or overlay
- structured parsing
- endpoint resolution
- content normalization

### Backend

A backend skill is operational machinery.
It exists so the visible capabilities can run reliably, but it should not compete as the main user-facing route.

Some backend skills are tightly coupled to a client-facing workflow, such as changing a charger endpoint and then verifying persistence. They remain Backend because the user is not asking for the low-level procedure itself; they are asking for the higher-level outcome.

Examples:
- IMAP / SMTP transport
- OAuth refresh and credential setup
- scheduler and clock rails
- API session management
- persistence checks
- endpoint verification
- low-level adapters

## Decision rule

Use this order when classifying a skill:

1. Can the user ask for it as a direct outcome?
   - Yes -> Frontend
2. If not, does it mainly enable a frontend skill to succeed?
   - Yes -> Services
3. If not, is it hidden operational plumbing?
   - Yes -> Backend

## Profiling fields

Every skill should ideally be tagged with:

- Primary layer: frontend / services / backend
- Visibility: user-facing / hidden
- Intention: what the user is trying to achieve
- Input: the contract accepted by the skill
- Output: the artifact or side effect produced
- Dependencies: skills or systems it relies on
- Status: canonical / helper / alias / candidate

## Initial profile for the current working set

This is the current first-pass profile for the most important skills in the active Hermes / Grid Code stack.

| Skill | Primary layer | Visibility | Role | Status |
|---|---|---:|---|---|
| `ticket-handler` | Frontend | User-facing | Support ticket actions and responses | Canonical |
| `calendar-meet-host-gridcode` | Frontend | User-facing | Create and manage meetings | Canonical |
| `google-workspace` | Services | Hidden | Workspace API bridge for Drive / Calendar | Canonical |
| `send-email-with-signature` | Frontend | User-facing | Send signed email via the mail rail | Canonical |
| `mail-imap-only-lock` | Backend | Hidden | IMAP / SMTP mail transport and locking | Canonical |
| `dario-executive-mail-review` | Frontend | User-facing | Mail review and triage workflow | Canonical |
| `gridcode-technical-service-report-pdf` | Frontend | User-facing | Technical service report generation | Canonical |
| `gridcode-preliminary-analysis-report` | Frontend | User-facing | Preliminary analysis report generation | Canonical |
| `gridcode-preliminary-report-a4-lite` | Frontend | User-facing | Lightweight preset of preliminary analysis | Alias / preset |
| `gridcodear-documentos` | Services | Hidden | Canonical Grid Code document factory for technical, administrative, and commercial PDFs | Canonical |
| `onsite-mobile-pdf-form-design` | Frontend | User-facing | Editable onsite form generation | Canonical |
| `nano-pdf` | Services | Hidden | PDF micro-edits and lightweight transforms | Helper |
| `pdf-overlay-hotfix` | Services | Hidden | Quick PDF correction / overlay operations | Helper |
| `gridcode-aggregated-behavior-remote-analysis` | Frontend | User-facing | Remote technical analysis workflow | Canonical |
| `ocpp-log-unpack-7d-analysis` | Services | Hidden | OCPP log unpacking helper | Helper |
| `webasto-unite-log-analysis-production-report` | Frontend | User-facing | Webasto log analysis report workflow | Canonical |
| `webasto-full-production-run` | Frontend | User-facing | Full production flow for Webasto | Canonical |
| `webasto-set-ocpp-endpoint` | Backend | Hidden | OCPP endpoint configuration | Helper |
| `webasto-verify-ocpp-persistence` | Backend | Hidden | Persistence validation for OCPP endpoint | Helper |
| `nuba-full-production-run` | Frontend | User-facing | Full production NUBA workflow | Canonical |
| `nuba-login-check` | Backend | Hidden | Access verification for NUBA | Helper |
| `linkedin-li-preset-v1` | Frontend | User-facing | LinkedIn high-level workflow preset | Canonical |
| `linkedin-message-standard-v1` | Services | Hidden | Message composition helper | Helper |
| `linkedin-posting-random-window-v1` | Services | Hidden | Posting window orchestration | Helper |
| `linkedin-trend-intensity-3w` | Services | Hidden | Trend analysis helper | Helper |
| `youtube-content` | Frontend | User-facing | YouTube transcript and content transformation | Canonical |
| `mindcode-create-discussion` | Frontend | User-facing | Create a MindCode discussion | Canonical |
| `google-meet-capture` | Services | Hidden | Meeting subtitle / transcript capture | Helper |
| `skill-observability` | Backend | Hidden | Skill telemetry and governance | Candidate |
| `skill-blacksmith` | Backend | Hidden | Skill hardening and fabrication pipeline | Candidate |
| `contact-enrichment` | Services | Hidden | Contact data enrichment support | Candidate |

## How to use this taxonomy

- Public skills should live and behave like frontend skills even if they rely on hidden services.
- A reusable capability should be promoted to a service instead of duplicated across multiple skills.
- Low-level plumbing should stay backend so it never competes with the user's real goal.
- If two skills share the same user intent, keep one frontend skill and turn the rest into services, helpers, or aliases.

## Maintaining the profile

When a new skill is added or an old one is refactored, update its primary layer here first.
If the profile is unclear, default to the visible user outcome rather than the internal mechanism.

This document is the canonical place to align strategy before touching individual SKILL.md files.

For the current working set of 40 principal capabilities, see [Los 40 Principales](/docs/reference/forty-principals).
For the broader first-pass repository profile, see [Skills Profile Index](/docs/reference/skills-profile-index).
For overlap and desduplication decisions, see [Collision Audit](/docs/reference/collision-audit).
For partial or incomplete capabilities, see [Partial Skills Audit](/docs/reference/partials-audit).
