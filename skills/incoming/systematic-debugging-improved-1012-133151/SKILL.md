---
name: systematic-debugging
description: Use when bugs are complex, high-risk, flaky, multi-component, or prior fixes failed; simple obvious bugs may be fixed directly and verified.
---

# Systematic Debugging

## Core Principle

Find root cause before fixing when the issue is complex, high-risk, uncertain, or already resisted fixes. For simple, obvious defects, fix directly and verify.

A symptom fix is a failure when it leaves the root cause unresolved.

## When to Use Full Process

Use when:
- Cannot reproduce reliably
- Error is deep in call stack or spans multiple components
- Production, performance, build, or integration issue with unclear cause
- 2+ attempted fixes failed
- Change is high-risk

Skip full process for simple typo/config/obvious one-line bugs. Still verify.

## Fast Path

For clear defects:
1. State root cause in one sentence.
2. Make the smallest fix.
3. Run focused test/repro and relevant regression.

No phase gates. No mandatory investigation ritual.

## Investigation Checklist

Use as needed, not sequential.

- Read full error/stack trace. Note file, line, code, warnings.
- Reproduce only if uncertain, flaky, or production-only. Otherwise record exact trigger and conditions.
- Check recent changes: git diff, commits, dependencies, config, environment.
- Multi-component systems: log data entering/exiting each boundary, config propagation, and state per layer. Run once, then locate failing layer.
- Deep call stack: trace bad value upstream until origin. Fix source, not symptom.

## Pattern Analysis

- Find similar working code in same codebase.
- If applying a pattern, read reference implementation completely.
- List every difference between working and broken, including small ones.
- Check dependencies, config, environment, assumptions.

## Hypothesis and Testing

- Write one specific hypothesis: "X is root cause because Y."
- Test with the smallest possible single change.
- If it fails, form a new hypothesis. Do not stack fixes.
- If you don't know, say so. Research or ask.

## Fix and Verify

- Create a failing test first only if defect boundary is unclear or regression risk is high. Otherwise a minimal repro/script is acceptable.
- Implement one root-cause fix. No "while I'm here" refactors.
- Verify: focused test passes, related tests pass, issue resolved. Do not claim success before verification.
- If fix fails: count attempts. Under 3, return to investigation with new information. At 3+, stop and question architecture.

### 3+ Fixes Failed: Question Architecture

Red flags:
- Each fix reveals new shared state/coupling elsewhere.
- Fixes require massive refactoring.
- Each fix creates new symptoms.

Stop and ask:
- Is this pattern fundamentally sound?
- Are we continuing through inertia?
- Should we refactor vs. keep fixing symptoms?

Discuss with your human partner before more fixes.

## Red Flags

Stop if you think:
- "Quick fix now, investigate later"
- "Try changing X and see"
- "Add multiple changes, run tests"
- "Skip the test, manually verify"
- "It's probably X"
- "One more fix" after 2+ failures
- Each fix reveals a new problem elsewhere

When human says:
- "Stop guessing"
- "Will it show us...?"
- "Ultra-think this"
- "We're stuck?"

Stop. Gather evidence. Return to investigation or question fundamentals.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple" | Simple bugs have root causes. Fast path is allowed, but still verify. |
| "Emergency, no time" | Systematic debugging is faster than thrashing. Obvious fixes may go direct. |
| "Already tried fixes" | 2+ failures means investigate or question architecture, not attempt Fix #3 blindly. |