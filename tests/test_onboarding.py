import asyncio

import pytest

from src.onboarding.application.tool_control import ControlledToolRegistry
from src.onboarding.adapters.groq_response import (
    FallbackResponseGenerator,
    GroqOrchestrationAdvisor,
    GroqResponseGenerator,
)
from src.onboarding.adapters.mocks import TemplateResponseGenerator
from src.onboarding.adapters.persistence import InMemoryAuditRepository, PublishingAuditRepository
from src.onboarding.bootstrap import build_container
from src.onboarding.domain.models import AuditEvent, IdentityResult, RiskResult, ToolNotAllowed
from src.onboarding.domain.models import OnboardingStatus, Prospect, StepStatus


def test_happy_path_prepares_documents() -> None:
    async def scenario() -> None:
        container = build_container()
        orchestrator, audit = container.orchestrator, container.audit_repository
        state = await orchestrator.start(Prospect("Juan Perez", "1712345678", "cuenta_ahorros"))

        assert state.status == OnboardingStatus.APPROVED
        assert state.documentation is not None
        assert "contrato_cuenta" in state.documentation.required_documents
        assert state.step_count <= 10
        events = await audit.list_for(state.onboarding_id)
        assert any(event.action == "verification_decision" for event in events)

    asyncio.run(scenario())


def test_low_identity_confidence_escalates() -> None:
    async def scenario() -> None:
        container = build_container()
        orchestrator, audit = container.orchestrator, container.audit_repository
        state = await orchestrator.start(Prospect("Juan Perez", "1712345999", "cuenta_ahorros"))

        assert state.status == OnboardingStatus.ESCALATED
        assert state.escalation is not None
        assert "Confianza" in state.escalation.reason
        assert state.documentation is None
        assert any(event.status == "escalated" for event in await audit.list_for(state.onboarding_id))

    asyncio.run(scenario())


def test_high_risk_escalates() -> None:
    async def scenario() -> None:
        orchestrator = build_container().orchestrator
        state = await orchestrator.start(Prospect("Persona Riesgo Alto", "1712345678", "cuenta_ahorros"))
        assert state.status == OnboardingStatus.ESCALATED
        assert state.risk is not None and state.risk.risk_level == "high"

    asyncio.run(scenario())


def test_tool_allowlist_is_enforced() -> None:
    async def scenario() -> None:
        async def forbidden_tool() -> str:
            return "should never run"

        registry = ControlledToolRegistry(
            tools={"prepare_documentation": forbidden_tool},
            allowlists={"identity_agent": {"verify_identity"}},
        )
        with pytest.raises(ToolNotAllowed):
            await registry.invoke("identity_agent", "prepare_documentation")

    asyncio.run(scenario())


def test_step_limit_escalates_automatically() -> None:
    async def scenario() -> None:
        orchestrator = build_container(max_steps=1).orchestrator
        state = await orchestrator.start(Prospect("Juan Perez", "1712345678", "cuenta_ahorros"))

        assert state.status == OnboardingStatus.ESCALATED
        assert state.escalation is not None
        assert "StepLimitExceeded" in state.escalation.reason
        assert state.step_count == 1

    asyncio.run(scenario())


def test_global_timeout_escalates_automatically() -> None:
    async def scenario() -> None:
        orchestrator = build_container(timeout_seconds=0.001).orchestrator
        state = await orchestrator.start(Prospect("Juan Perez", "1712345678", "cuenta_ahorros"))

        assert state.status == OnboardingStatus.ESCALATED
        assert state.escalation is not None
        assert "Tiempo global" in state.escalation.reason

    asyncio.run(scenario())


def test_audit_events_are_published() -> None:
    async def scenario() -> None:
        class FakePublisher:
            def __init__(self) -> None:
                self.events: list[AuditEvent] = []

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

            async def publish(self, event: AuditEvent) -> None:
                self.events.append(event)

        publisher = FakePublisher()
        audit = PublishingAuditRepository(InMemoryAuditRepository(), [publisher])
        event = AuditEvent(
            event_id="event-1",
            onboarding_id="onboarding-1",
            step=1,
            actor="orchestrator",
            action="verification_decision",
            status=StepStatus.DECISION,
            details={"outcome": "continue"},
        )

        await audit.start()
        await audit.append(event)
        await audit.stop()

        assert publisher.events == [event]
        assert await audit.list_for("onboarding-1") == [event]

    asyncio.run(scenario())


def test_groq_stream_is_accumulated_without_sending_document_id() -> None:
    async def scenario() -> None:
        class Stream:
            def __init__(self) -> None:
                self._parts = iter(["Hola, ", "tu solicitud fue aprobada."])

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    content = next(self._parts)
                except StopIteration:
                    raise StopAsyncIteration
                delta = type("Delta", (), {"content": content})()
                choice = type("Choice", (), {"delta": delta})()
                return type("Chunk", (), {"choices": [choice]})()

        class Completions:
            def __init__(self) -> None:
                self.kwargs = None

            async def create(self, **kwargs):
                self.kwargs = kwargs
                return Stream()

        completions = Completions()
        fake_chat = type("Chat", (), {"completions": completions})()
        fake_client = type("Client", (), {"chat": fake_chat})()
        generator = GroqResponseGenerator("test-key")
        generator._client = fake_client

        message = await generator.generate(
            Prospect("Juan Perez", "1712345678", "cuenta_ahorros"), True, None
        )

        assert message == "Hola, tu solicitud fue aprobada."
        assert completions.kwargs["stream"] is True
        assert completions.kwargs["model"] == "openai/gpt-oss-20b"
        assert completions.kwargs["reasoning_effort"] == "medium"
        assert "1712345678" not in str(completions.kwargs["messages"])
        assert "Juan Perez" not in str(completions.kwargs["messages"])

    asyncio.run(scenario())


def test_orchestrator_uses_120b_model() -> None:
    async def scenario() -> None:
        class Stream:
            def __init__(self) -> None:
                self._parts = iter(
                    ['{"decision":"continue",', '"explanation":"Validaciones consistentes."}']
                )

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    content = next(self._parts)
                except StopIteration:
                    raise StopAsyncIteration
                delta = type("Delta", (), {"content": content})()
                choice = type("Choice", (), {"delta": delta})()
                return type("Chunk", (), {"choices": [choice]})()

        class Completions:
            def __init__(self) -> None:
                self.kwargs = None

            async def create(self, **kwargs):
                self.kwargs = kwargs
                return Stream()

        completions = Completions()
        fake_chat = type("Chat", (), {"completions": completions})()
        advisor = GroqOrchestrationAdvisor(
            "test-key", model="openai/gpt-oss-120b"
        )
        advisor._client = type("Client", (), {"chat": fake_chat})()

        advice = await advisor.advise(
            IdentityResult(True, 0.96), RiskResult("low", [])
        )

        assert advice.decision == "continue"
        assert completions.kwargs["model"] == "openai/gpt-oss-120b"
        assert completions.kwargs["stream"] is True

    asyncio.run(scenario())


def test_groq_failure_uses_deterministic_fallback() -> None:
    async def scenario() -> None:
        class FailingGenerator:
            async def generate(self, prospect, approved, reason):
                raise RuntimeError("provider unavailable")

        generator = FallbackResponseGenerator(
            FailingGenerator(), TemplateResponseGenerator()
        )
        message = await generator.generate(
            Prospect("Juan Perez", "1712345678", "cuenta_ahorros"), True, None
        )
        assert "Juan Perez" in message

    asyncio.run(scenario())

