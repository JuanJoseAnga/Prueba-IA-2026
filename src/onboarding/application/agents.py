from __future__ import annotations

from dataclasses import replace

from src.onboarding.application.ports import SpecialistExplainer
from src.onboarding.application.tool_control import ControlledToolRegistry
from src.onboarding.domain.models import (
    DocumentationResult,
    IdentityResult,
    Prospect,
    RiskResult,
)


class IdentityAgent:
    name = "identity_agent"

    def __init__(self, tools: ControlledToolRegistry, explainer: SpecialistExplainer) -> None:
        self._tools = tools
        self._explainer = explainer

    async def run(self, prospect: Prospect) -> IdentityResult:
        result = await self._tools.invoke(
            self.name, "verify_identity", document_id=prospect.document_id
        )
        explanation = await self._explainer.explain(
            "identity", {"verified": result.verified, "confidence": result.confidence}
        )
        return replace(result, explanation=explanation)


class RiskAgent:
    name = "risk_agent"

    def __init__(self, tools: ControlledToolRegistry, explainer: SpecialistExplainer) -> None:
        self._tools = tools
        self._explainer = explainer

    async def run(self, prospect: Prospect) -> RiskResult:
        result = await self._tools.invoke(
            self.name,
            "check_risk_lists",
            name=prospect.name,
            document_id=prospect.document_id,
        )
        explanation = await self._explainer.explain(
            "risk",
            {"risk_level": result.risk_level, "match_count": len(result.matches)},
        )
        return replace(result, explanation=explanation)


class DocumentationAgent:
    name = "documentation_agent"

    def __init__(self, tools: ControlledToolRegistry, explainer: SpecialistExplainer) -> None:
        self._tools = tools
        self._explainer = explainer

    async def run(self, prospect: Prospect) -> DocumentationResult:
        result = await self._tools.invoke(
            self.name,
            "prepare_documentation",
            product=prospect.product,
            client_data={"name": prospect.name, "document_id": prospect.document_id},
        )
        explanation = await self._explainer.explain(
            "documentation",
            {"product": prospect.product, "required_documents": result.required_documents},
        )
        return replace(result, explanation=explanation)


class ResponseAgent:
    name = "response_agent"

    def __init__(self, tools: ControlledToolRegistry) -> None:
        self._tools = tools

    async def run(self, prospect: Prospect, approved: bool, reason: str | None = None) -> str:
        return await self._tools.invoke(
            self.name,
            "generate_customer_response",
            prospect=prospect,
            approved=approved,
            reason=reason,
        )

