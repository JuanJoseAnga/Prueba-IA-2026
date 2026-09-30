from __future__ import annotations

import asyncio
from uuid import uuid4

from src.onboarding.domain.models import (
    DocumentationResult,
    Escalation,
    IdentityResult,
    OrchestrationAdvice,
    Prospect,
    RiskResult,
)


class MockBankTools:
    """Mocks deterministas reemplazables por APIs reales en adaptadores de salida."""

    async def verify_identity(self, document_id: str) -> IdentityResult:
        await asyncio.sleep(0.01)
        if document_id.endswith("000"):
            return IdentityResult(verified=False, confidence=0.95)
        if document_id.endswith("999"):
            return IdentityResult(verified=True, confidence=0.65)
        return IdentityResult(verified=True, confidence=0.96)

    async def check_risk_lists(self, name: str, document_id: str) -> RiskResult:
        await asyncio.sleep(0.01)
        normalized = name.casefold()
        if "riesgo alto" in normalized:
            return RiskResult(risk_level="high", matches=["MOCK-LIST-001"])
        if "riesgo medio" in normalized:
            return RiskResult(risk_level="medium", matches=["MOCK-REVIEW-001"])
        return RiskResult(risk_level="low", matches=[])

    async def prepare_documentation(
        self, product: str, client_data: dict[str, str]
    ) -> DocumentationResult:
        await asyncio.sleep(0.01)
        by_product = {
            "cuenta_ahorros": ["contrato_cuenta", "declaracion_origen_fondos", "tratamiento_datos"],
            "cuenta_corriente": ["contrato_cuenta", "declaracion_origen_fondos", "tratamiento_datos", "referencias"],
        }
        return DocumentationResult(
            required_documents=by_product.get(product, ["formulario_producto", "tratamiento_datos"])
        )


class InMemoryHumanEscalation:
    def __init__(self) -> None:
        self.cases: list[Escalation] = []

    async def escalate(self, onboarding_id: str, reason: str) -> Escalation:
        case = Escalation(case_id=f"HUM-{uuid4().hex[:10].upper()}", reason=reason)
        self.cases.append(case)
        return case


class TemplateResponseGenerator:
    async def generate(self, prospect: Prospect, approved: bool, reason: str | None) -> str:
        if approved:
            return f"Hola {prospect.name}, tus validaciones finalizaron correctamente. Continuaremos con la apertura de tu {prospect.product}."
        return f"Hola {prospect.name}, tu solicitud está siendo revisada por un especialista. No necesitas enviarla nuevamente."


class TemplateSpecialistExplainer:
    async def explain(self, specialty: str, context: dict[str, object]) -> str:
        return f"Evaluación {specialty} completada con reglas deterministas."


class PolicyOrchestrationAdvisor:
    async def advise(
        self, identity: IdentityResult, risk: RiskResult
    ) -> OrchestrationAdvice:
        return OrchestrationAdvice(
            decision="continue",
            explanation="Las políticas deterministas decidirán el resultado.",
        )

