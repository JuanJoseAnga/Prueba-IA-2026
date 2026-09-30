from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, Awaitable, Callable
from uuid import uuid4

from src.onboarding.application.agents import (
    DocumentationAgent,
    IdentityAgent,
    ResponseAgent,
    RiskAgent,
)
from src.onboarding.application.ports import (
    AuditPort,
    HumanEscalationPort,
    OrchestrationAdvisor,
    StateRepository,
)
from src.onboarding.domain.models import (
    AuditEvent,
    OnboardingState,
    OnboardingStatus,
    Prospect,
    StepStatus,
)


class OnboardingOrchestrator:
    def __init__(
        self,
        identity_agent: IdentityAgent,
        risk_agent: RiskAgent,
        documentation_agent: DocumentationAgent,
        response_agent: ResponseAgent,
        orchestration_advisor: OrchestrationAdvisor,
        escalation: HumanEscalationPort,
        audit: AuditPort,
        states: StateRepository,
        *,
        max_steps: int = 10,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._identity_agent = identity_agent
        self._risk_agent = risk_agent
        self._documentation_agent = documentation_agent
        self._response_agent = response_agent
        self._orchestration_advisor = orchestration_advisor
        self._escalation = escalation
        self._audit = audit
        self._states = states
        self._max_steps = max_steps
        self._timeout_seconds = timeout_seconds

    async def start(self, prospect: Prospect) -> OnboardingState:
        state = OnboardingState(onboarding_id=str(uuid4()), prospect=prospect)
        await self._states.save(state)
        await self._record(state, "orchestrator", "request_received", StepStatus.COMPLETED)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._execute(state)
        except TimeoutError:
            await self._escalate(
                state, f"Tiempo global de {self._timeout_seconds:g} segundos excedido"
            )
        except Exception as exc:
            await self._record(
                state,
                "orchestrator",
                "unexpected_error",
                StepStatus.FAILED,
                {"error_type": type(exc).__name__, "message": str(exc)},
                consume_step=False,
            )
            await self._escalate(state, f"Error técnico: {type(exc).__name__}")

        await self._states.save(state)
        return state

    async def _execute(self, state: OnboardingState) -> None:
        state.status = OnboardingStatus.VERIFYING
        identity, risk = await asyncio.gather(
            self._run_agent(state, self._identity_agent.name, "verify_identity", lambda: self._identity_agent.run(state.prospect)),
            self._run_agent(state, self._risk_agent.name, "check_risk_lists", lambda: self._risk_agent.run(state.prospect)),
        )
        state.identity = identity
        state.risk = risk

        advice = await self._run_agent(
            state,
            "orchestrator_agent",
            "evaluate_with_llm",
            lambda: self._orchestration_advisor.advise(identity, risk),
        )
        reason = self._review_reason(state)
        if reason is None and advice.decision == "escalate":
            reason = "El agente orquestador recomienda revisión humana"
        if reason:
            await self._record(
                state,
                "orchestrator",
                "verification_decision",
                StepStatus.DECISION,
                {
                    "outcome": "escalate",
                    "reason": reason,
                    "llm_advice": asdict(advice),
                },
            )
            await self._escalate(state, reason)
            return

        await self._record(
            state,
            "orchestrator",
            "verification_decision",
            StepStatus.DECISION,
            {"outcome": "continue", "llm_advice": asdict(advice)},
        )
        state.status = OnboardingStatus.PREPARING_DOCUMENTS
        state.documentation = await self._run_agent(
            state,
            self._documentation_agent.name,
            "prepare_documentation",
            lambda: self._documentation_agent.run(state.prospect),
        )
        state.customer_message = await self._run_agent(
            state,
            self._response_agent.name,
            "generate_customer_response",
            lambda: self._response_agent.run(state.prospect, True),
        )
        state.status = OnboardingStatus.APPROVED

    @staticmethod
    def _review_reason(state: OnboardingState) -> str | None:
        assert state.identity is not None and state.risk is not None
        if not state.identity.verified:
            return "La identidad no pudo ser verificada"
        if state.identity.confidence < 0.8:
            return f"Confianza de identidad insuficiente ({state.identity.confidence:.2f})"
        if state.risk.risk_level == "high":
            return "Coincidencia de riesgo alto"
        if state.risk.risk_level == "medium":
            return "Riesgo medio ambiguo; se requiere criterio humano"
        return None

    async def _run_agent(
        self,
        state: OnboardingState,
        actor: str,
        action: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        await self._record(state, actor, action, StepStatus.STARTED)
        try:
            result = await operation()
        except Exception as exc:
            await self._record(
                state,
                actor,
                action,
                StepStatus.FAILED,
                {"error_type": type(exc).__name__, "message": str(exc)},
                consume_step=False,
            )
            raise
        await self._record(
            state, actor, action, StepStatus.COMPLETED, {"result": asdict(result) if hasattr(result, "__dataclass_fields__") else result}, consume_step=False
        )
        return result

    async def _escalate(self, state: OnboardingState, reason: str) -> None:
        if state.escalation is None:
            state.escalation = await self._escalation.escalate(state.onboarding_id, reason)
        state.status = OnboardingStatus.ESCALATED
        state.customer_message = await self._response_agent.run(state.prospect, False, reason)
        await self._record(
            state,
            "orchestrator",
            "human_escalation",
            StepStatus.ESCALATED,
            {"case_id": state.escalation.case_id, "reason": reason},
            consume_step=False,
        )

    async def _record(
        self,
        state: OnboardingState,
        actor: str,
        action: str,
        status: StepStatus,
        details: dict[str, Any] | None = None,
        *,
        consume_step: bool = True,
    ) -> None:
        step = state.next_step(self._max_steps) if consume_step else state.step_count
        await self._audit.append(
            AuditEvent(
                event_id=str(uuid4()),
                onboarding_id=state.onboarding_id,
                step=step,
                actor=actor,
                action=action,
                status=status,
                details=details or {},
            )
        )

