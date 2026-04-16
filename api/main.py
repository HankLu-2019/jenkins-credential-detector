"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import builds, exemptions, findings, stats

app = FastAPI(
    title="Jenkins Log Sentinel",
    description="Credential leak detector for Jenkins build logs",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(findings.router)
app.include_router(builds.router)
app.include_router(exemptions.router)
app.include_router(stats.router)


@app.get("/health")
def health():
    return {"status": "ok"}
