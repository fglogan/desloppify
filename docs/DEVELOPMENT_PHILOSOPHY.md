# Development Philosophy

Desloppify is built to optimize agent behavior, not to maximize human-facing UX or stable integration APIs.

## 1) Agent-First, Not Human-First

This project is primarily for AI agents operating on codebases.
It is not designed first for direct human interaction, and it is not optimized for broad programmatic embedding as a stable platform.
Where tradeoffs are required, agent effectiveness wins.

## 2) No Compatibility Promise

Because this is a tool for agents, we do not commit to long-term backward compatibility across versions.
We will not maintain compatibility layers solely to preserve old integrations.
If you need a fixed contract, pin a version or fork the project.
Temporary migration shims are acceptable only when they have a short, explicit removal window.

## 3) Build a North-Star Objective for Agents

The core mission is to define a clear target that agents can optimize toward.
We collect signals, ask structured questions, and combine objective and subjective evidence into a north-star score.
That score is the optimization target.
Most modern reasoning assistants are post-trained with reward and preference objectives; our north-star score serves as an external objective that further steers their behavior.

## 4) Make the Target Hard to Game

A useful score must be robust against gaming.
We prioritize metrics and evaluation methods that reward real codebase quality, not superficial compliance.
For subjective checks, we add guardrails and cross-checks to reduce exploitability.

## 5) Language-Agnostic by Design

The foundation of this package should apply across languages.
Language-specific implementations can differ, but the governing principles and scoring intent remain consistent.
Our direction is broad language coverage without sacrificing conceptual consistency.

## 6) Architectural Contracts Must Be Concrete

Architecture rules should be explicit, testable, and documented:

- Keep command entry files as orchestrators; push behavior into focused flow modules.
- Restrict dynamic import behavior to designated extension points (`languages/__init__.py`, `hook_registry.py`).
- Keep persisted-state ownership in `state.py`/`engine/state_internal`; treat command-layer state as orchestration only.
- Back each major boundary with focused regression tests so refactors stay behavior-preserving.
