# Interview Demo Pack

This document explains how to demo Mini-OpenClaw as an interview assistant rather than a generic local chat app.

## What is included

- Focused knowledge pack under `backend/knowledge/interview/`
- Two interview-specific skills:
  - `backend/skills/interview_answer_builder/SKILL.md`
  - `backend/skills/resume_story_coach/SKILL.md`
- A prompt sheet at `backend/workspace/INTERVIEW_DEMO.md`
- Frontend entry points for demo prompts and inspector access

## Demo workflow

1. Start the app and open the main chat workspace.
2. In the Interview demo section, click one of the seeded prompts.
3. Let the assistant answer in chat.
4. Open Runtime diagnostics to inspect the run.
5. Show the Graph retrieval diagnostics card when graph-assisted retrieval metadata is present.
6. Open the inspector on `INTERVIEW_DEMO.md` or one of the interview skills.
7. Explain how evals, traces, memory, graph-assisted retrieval, and failure handling support the story.

## Graph-assisted Retrieval Pitch

Mini-OpenClaw now includes a lightweight, Graph-RAG-inspired retrieval layer. It builds an inspectable JSON graph from local knowledge docs, skills, workspace files, and traces, then lets retrieval expand from direct matches to related evidence.

This is intentionally not a full Microsoft-style GraphRAG system with community detection and global summary generation. The interview-safe framing is: graph-assisted retrieval helps when a question needs to connect multiple project artifacts, such as eval notes plus interview prompts plus trace diagnostics. It is unnecessary for simple keyword questions where the direct document already contains the answer.

## Seed prompts

- Summarize Mini-OpenClaw as a resume-ready AI agent project in 4 bullets.
- Explain why the project uses transparent file-based memory instead of only hidden vector memory.
- Pretend you are an interviewer. Ask me 5 hard follow-up questions about Mini-OpenClaw's evals, traces, and failure handling.
- Turn this project into a 90-second interview answer that sounds practical instead of hype-driven.
- Compare the engineering value of evals, observability, and user isolation in this project.
- Rewrite Mini-OpenClaw into a STAR story about improving an AI agent from prototype to credible engineering project.
- Explain the Graph-RAG-inspired retrieval layer without overselling it as full GraphRAG.

## Screenshot checklist

- Main chat page with one seeded interview prompt in progress
- Completed assistant answer with reasoning trace expanded
- Runtime diagnostics showing status, latency, and any failure metadata
- Runtime diagnostics showing graph retrieval direct nodes, expanded evidence, or the neutral empty state
- Inspector open on `INTERVIEW_DEMO.md`
- Inspector open on `interview_answer_builder/SKILL.md` or `resume_story_coach/SKILL.md`
