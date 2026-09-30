from __future__ import annotations

from typing import Any, Protocol

from src.onboarding.domain.models import (
    AuditEvent,
    DocumentationResult,
    Escalation,
    IdentityResult,
    OrchestrationAdvice,
    Prospect,
    RiskResult,
)


class IdentityVerifier(Protocol):
    async def verify_identity(self, document_id: str) -> IdentityResult: ...


class RiskListChecker(Protocol):
    async def check_risk_lists(self, name: str, document_id: str) -> RiskResult: ...


class DocumentationPreparer(Protocol):
    async def prepare_documentation(
        self, product: str, client_data: dict[str, Any]
    ) -> DocumentationResult: ...


class HumanEscalationPort(Protocol):
    async def escalate(self, onboarding_id: str, reason: str) -> Escalation: ...


class AuditPort(Protocol):
    async def append(self, event: AuditEvent) -> None: ...

    async def list_for(self, onboarding_id: str) -> list[AuditEvent]: ...


class StateRepository(Protocol):
    async def save(self, state: Any) -> None: ...

    async def get(self, onboarding_id: str) -> Any | None: ...


class CustomerResponseGenerator(Protocol):
    async def generate(self, prospect: Prospect, approved: bool, reason: str | None) -> str: ...


class SpecialistExplainer(Protocol):
    async def explain(self, specialty: str, context: dict[str, Any]) -> str: ...


class OrchestrationAdvisor(Protocol):
    async def advise(
        self, identity: IdentityResult, risk: RiskResult
    ) -> OrchestrationAdvice: ...

