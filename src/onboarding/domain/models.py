from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class OnboardingStatus(StrEnum):
    RECEIVED = "received"
    VERIFYING = "verifying"
    PREPARING_DOCUMENTS = "preparing_documents"
    APPROVED = "approved"
    ESCALATED = "escalated"
    FAILED = "failed"


class StepStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    DECISION = "decision"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class Prospect:
    name: str
    document_id: str
    product: str


@dataclass(frozen=True)
class IdentityResult:
    verified: bool
    confidence: float
    explanation: str | None = None


@dataclass(frozen=True)
class RiskResult:
    risk_level: str
    matches: list[str]
    explanation: str | None = None


@dataclass(frozen=True)
class DocumentationResult:
    required_documents: list[str]
    explanation: str | None = None


@dataclass(frozen=True)
class OrchestrationAdvice:
    decision: str
    explanation: str


@dataclass(frozen=True)
class Escalation:
    case_id: str
    reason: str


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    onboarding_id: str
    step: int
    actor: str
    action: str
    status: StepStatus
    details: dict[str, Any]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OnboardingState:
    onboarding_id: str
    prospect: Prospect
    status: OnboardingStatus = OnboardingStatus.RECEIVED
    step_count: int = 0
    identity: IdentityResult | None = None
    risk: RiskResult | None = None
    documentation: DocumentationResult | None = None
    escalation: Escalation | None = None
    customer_message: str | None = None

    def next_step(self, max_steps: int) -> int:
        if self.step_count >= max_steps:
            raise StepLimitExceeded(f"Se alcanzó el límite de {max_steps} pasos")
        self.step_count += 1
        return self.step_count


class OnboardingError(Exception):
    """Error base del caso de uso."""


class StepLimitExceeded(OnboardingError):
    pass


class ToolNotAllowed(OnboardingError):
    pass

