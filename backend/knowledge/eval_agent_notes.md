# Evaluation notes for Mini-OpenClaw

Mini-OpenClaw should not stop at a runnable chat UI. The project becomes stronger when it is measurable, explainable, and easy to diagnose.

## Why evaluation matters

- We need a task success rate instead of vague anecdotal demos.
- We need to know whether memory, skills, and retrieval actually help.
- We need structured failure categories so regressions are visible.

## Interview positioning

For interview demos, emphasize that Mini-OpenClaw is a transparent local Agent workspace with file-based memory, inspectable skills, and an engineering loop around evaluation and observability.

## What to measure

- task success rate
- tool call success rate
- average end-to-end latency
- average tool calls per task
- failure category distribution
