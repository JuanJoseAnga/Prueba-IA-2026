from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.onboarding.bootstrap import build_container
from src.onboarding.application.orchestrator import OnboardingOrchestrator
from src.onboarding.domain.models import Prospect


class StartOnboardingRequest(BaseModel):
    prospect_name: str = Field(min_length=2, max_length=120)
    document_id: str = Field(pattern=r"^[A-Za-z0-9-]{5,30}$")
    product: str = Field(min_length=3, max_length=50)


class OnboardingResponse(BaseModel):
    onboarding_id: str
    status: str
    step_count: int
    identity: dict[str, Any] | None
    risk: dict[str, Any] | None
    documentation: dict[str, Any] | None
    escalation: dict[str, Any] | None
    customer_message: str | None
    audit: list[dict[str, Any]]


container = build_container(
    kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
    kafka_topic=os.getenv("KAFKA_AUDIT_TOPIC", "bank.onboarding.audit.v1"),
    database_url=os.getenv(
        "DATABASE_URL", "postgresql://onboarding:onboarding@localhost:5432/onboarding"
    ),
    groq_api_key=os.getenv("GROQ_API_KEY") or None,
    groq_specialist_model=os.getenv(
        "GROQ_SPECIALIST_MODEL", "openai/gpt-oss-20b"
    ),
    groq_orchestrator_model=os.getenv(
        "GROQ_ORCHESTRATOR_MODEL", "openai/gpt-oss-120b"
    ),
)
orchestrator = container.orchestrator
audit_repository = container.audit_repository


@asynccontextmanager
async def lifespan(_: FastAPI):
    await container.start()
    try:
        yield
    finally:
        await container.stop()


app = FastAPI(title="Onboarding Orchestrator", version="1.0.0", lifespan=lifespan)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def get_orchestrator() -> OnboardingOrchestrator:
    return orchestrator


@app.get("/", include_in_schema=False)
async def chat_frontend() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.post("/api/v1/onboarding/start", response_model=OnboardingResponse)
async def start_onboarding(
    request: StartOnboardingRequest,
    service: Annotated[OnboardingOrchestrator, Depends(get_orchestrator)],
) -> OnboardingResponse:
    state = await service.start(
        Prospect(
            name=request.prospect_name,
            document_id=request.document_id,
            product=request.product,
        )
    )
    events = await audit_repository.list_for(state.onboarding_id)
    payload = asdict(state)
    payload.pop("prospect")
    payload["audit"] = [asdict(event) for event in events]
    return OnboardingResponse.model_validate(payload)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

