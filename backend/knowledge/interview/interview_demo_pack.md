# Interview Assistant Demo Pack

This knowledge pack turns Mini-OpenClaw into a focused interview-prep workspace instead of a generic chat shell.

## What the assistant should help with

- turn a raw project into a resume-ready project story
- answer “why did you design it this way?” with concrete tradeoffs
- explain evaluation, observability, memory, and failure handling decisions
- prepare concise STAR-style examples for behavioral interviews
- rehearse follow-up questions about agent systems and local-first architecture

## Core project talking points

### 1. Why Mini-OpenClaw is not just a chat UI

Mini-OpenClaw is a transparent local agent workspace. The important value is not just that it can answer questions, but that it exposes:

- editable prompt surfaces
- inspectable skills
- file-based memory
- traceable tool calls
- measurable eval outputs
- explainable failure handling

### 2. Strong engineering story

When presenting this project, highlight that it now has:

- offline evaluation datasets and ablation profiles
- structured runtime traces with latency and error categories
- per-user storage isolation
- per-user async write serialization
- explicit failure fallbacks
- a vertical demo pack for interview prep

### 3. Good answers to expected interviewer questions

#### Q: Why file-based memory instead of a hidden vector database only?

A good answer:

Because the project optimizes for transparency and debuggability. File-based memory makes the agent state inspectable, editable, and easy to reason about in demos and interviews. Retrieval can still exist, but the baseline state stays human-readable.

#### Q: Why build local traces and evals?

A good answer:

Because agent demos are hard to trust without measurement and diagnostics. Local traces explain what happened on each run, and offline evals provide a repeatable way to compare capability changes like memory, retrieval, or skills.

#### Q: Why add user isolation so early?

A good answer:

Because cross-session contamination is one of the fastest ways an agent product loses trust. Even a minimal `X-User-ID` boundary shows that the architecture has already considered safety and productization.

## Demo flow

1. Open the Interview Demo prompt sheet.
2. Click one of the seeded prompts.
3. Ask the assistant to summarize Mini-OpenClaw as a resume project.
4. Open Runtime diagnostics to show traces, retries, and failure categories.
5. Open the interview skills docs to show the system is inspectable.

## High-signal interview themes

- agent engineering over prompt hacking
- transparent memory rather than hidden state
- evals and observability as first-class features
- graceful degradation when dependencies or tools fail
- incremental productization choices with minimal complexity
