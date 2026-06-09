---
sidebar_position: 10
title: "Partial Skills Audit"
description: "Resolved mapping for skills that were previously partial or incomplete"
---

# Partial Skills Audit

This page records how the previously partial or mention-only skills were resolved in this pass, with the 40 principals and the taxonomy used as the alignment reference.

Audit result for this pass: the 11 previously tracked items were found in the repo, mapped against the principal-capabilities index, and promoted out of Pending.

## Resolved items

| Skill | Layer | Final status | Decision | Notes |
|---|---|---|---|---|
| `1password` | Backend | Helper | Keep hidden support only | Secret-management plumbing, not a public user outcome |
| `agentmail` | Frontend | Canonical | Separate agent-owned inbox route | Distinct from the personal mail stack |
| `base` | Frontend | Canonical | Keep as chain-specific blockchain route | Base-specific wallet, token, and tx workflows |
| `godmode` | Frontend | Canonical | Keep as explicit red-teaming/jailbreak route | High-risk but real user-facing intent |
| `hermes-agent` | Frontend | Canonical | Keep as the Hermes usage / extension guide | User-facing support and contribution workflow |
| `neuroskill-bci` | Frontend | Canonical | Keep as the BCI/neurofeedback route | Requires local NeuroSkill + wearable hardware |
| `openclaw-migration` | Frontend | Canonical | Keep as migration route | One-shot import workflow for OpenClaw users |
| `openhue` | Frontend | Canonical | Keep as smart-home control route | Direct light / scene control capability |
| `oss-forensics` | Frontend | Canonical | Keep as security investigation route | Standardized forensic reporting workflow |
| `sherlock` | Frontend | Canonical | Keep as OSINT username search route | Direct username reconnaissance workflow |
| `solana` | Frontend | Canonical | Keep as chain-specific blockchain route | Solana-specific wallet, token, and NFT workflows |

## Partial-to-canonical rules

- If the intent is user-facing and the output can be standardized, promote it to canonical.
- If the skill only provides a step, transform it into a helper or service.
- If the skill is mostly plumbing, hide it in backend.
- If the skill overlaps with an existing canonical route, demote the duplicate and keep a single public entry point.

## De-duplication notes

- `agentmail` is separate from the personal mail rail because it gives the agent its own inbox identity.
- `base` and `solana` are chain-specific variants and should remain separate canonical routes.
- `openclaw-migration` is a one-shot migration route, not a permanent utility layer.
- `oss-forensics` and `sherlock` stay canonical only because they produce stable investigation outcomes.

## Next actions

1. Review each resolved item against the 40-principals map.
2. Keep helper-only pieces like `1password` out of the public surface.
3. Merge any remaining overlaps into the collision audit.
