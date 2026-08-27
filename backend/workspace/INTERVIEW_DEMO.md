# Interview Demo Workspace

Use this sheet to run the hiring-facing Mini-OpenClaw demo.

## Suggested prompts

1. Summarize Mini-OpenClaw as a resume-ready AI agent project in 4 bullets.
2. Explain why the project uses transparent file-based memory instead of only hidden vector memory.
3. Pretend you are an interviewer. Ask me 5 hard follow-up questions about Mini-OpenClaw's evals, traces, and failure handling.
4. Turn this project into a 90-second interview answer that sounds practical instead of hype-driven.
5. Compare the engineering value of evals, observability, and user isolation in this project.
6. Rewrite Mini-OpenClaw into a STAR story about improving an AI agent from prototype to credible engineering project.
7. Explain the Graph-RAG-inspired retrieval layer without overselling it as full GraphRAG.

## Live demo flow

- Open Runtime diagnostics after each answer.
- For graph-assisted retrieval prompts, show direct matches, expanded evidence, and the neutral empty state when no graph metadata exists.
- Show `SKILLS_SNAPSHOT.md` and the interview skills docs.
- Show this file to prove the demo is repeatable.
- If asked about Graph RAG, say this is a lightweight graph-assisted retrieval layer over local files and traces, not a full community-summarization GraphRAG system.
- If asked about future work, mention hosted auth, richer retrieval, stronger eval automation, and optional graph quality metrics.

## Screenshot checklist

- Chat answer using one of the interview prompts
- Runtime trace panel with status / latency / error category
- Runtime trace panel with graph retrieval diagnostics or neutral empty state
- Inspector open on `INTERVIEW_DEMO.md`
- Inspector open on one interview skill file
