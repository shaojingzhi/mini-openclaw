"""Mini-OpenClaw FastAPI backend application.

Run with: ``uvicorn backend.app:app --port 8002``
"""

from __future__ import annotations

from fastapi import FastAPI

app: FastAPI = FastAPI(title="Mini-OpenClaw Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8002, reload=False)
