from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.onboarding.adapters.mocks import (
    InMemoryHumanEscalation,
    MockBankTools,
    PolicyOrchestrationAdvisor,
    TemplateResponseGenerator,
    TemplateSpecialistExplainer,
)
from src.onboarding.adapters.persistence import InMemoryAuditRepository, InMemoryStateRepository
from src.onboarding.adapters.persistence import PublishingAuditRepository
from src.onboarding.application.agents import DocumentationAgent, IdentityAgent, ResponseAgent, RiskAgent
from src.onboarding.application.orchestrator import OnboardingOrchestrator
from src.onboarding.application.tool_control import ControlledToolRegistry


@dataclass
class ApplicationContainer:
    orchestrator: OnboardingOrchestrator
    audit_repository: PublishingAuditRepository
    resources: list[Any]

    async def start(self) -> None:
        for resource in self.resources:
            await resource.start()
        await self.audit_repository.start()

    async def stop(self) -> None:
        await self.audit_repository.stop()
        for resource in reversed(self.resources):
            await resource.stop()


def build_container(
    *,
    max_steps: int = 10,
    timeout_seconds: float = 30.0,
    kafka_bootstrap_servers: str | None = None,
    kafka_topic: str = "bank.onboarding.audit.v1",
    database_url: str | None = None,
    groq_api_key: str | None = None,
    groq_specialist_model: str = "openai/gpt-oss-20b",
    groq_orchestrator_model: str = "openai/gpt-oss-120b",
) -> ApplicationContainer:
    resources: list[Any] = []
    if database_url:
        from src.onboarding.adapters.postgres_tools import PostgresBankTools

        bank_tools = PostgresBankTools(database_url)
        resources.append(bank_tools)
    else:
        bank_tools = MockBankTools()
    publishers = []
    if kafka_bootstrap_servers:
        from src.onboarding.adapters.kafka_audit import KafkaAuditPublisher

        publishers.append(KafkaAuditPublisher(kafka_bootstrap_servers, kafka_topic))
    audit = PublishingAuditRepository(InMemoryAuditRepository(), publishers)
    response_generator = TemplateResponseGenerator()
    specialist_explainer = TemplateSpecialistExplainer()
    orchestration_advisor = PolicyOrchestrationAdvisor()
    if groq_api_key:
        from src.onboarding.adapters.groq_response import (
            FallbackOrchestrationAdvisor,
            FallbackResponseGenerator,
            FallbackSpecialistExplainer,
            GroqOrchestrationAdvisor,
            GroqResponseGenerator,
            GroqSpecialistExplainer,
        )

        groq_generator = GroqResponseGenerator(
            groq_api_key, model=groq_specialist_model
        )
        groq_explainer = GroqSpecialistExplainer(
            groq_api_key, model=groq_specialist_model
        )
        groq_advisor = GroqOrchestrationAdvisor(
            groq_api_key, model=groq_orchestrator_model
        )
        resources.extend([groq_generator, groq_explainer, groq_advisor])
        response_generator = FallbackResponseGenerator(
            groq_generator, response_generator
        )
        specialist_explainer = FallbackSpecialistExplainer(
            groq_explainer, specialist_explainer
        )
        orchestration_advisor = FallbackOrchestrationAdvisor(
            groq_advisor, orchestration_advisor
        )
    registry = ControlledToolRegistry(
        tools={
            "verify_identity": bank_tools.verify_identity,
            "check_risk_lists": bank_tools.check_risk_lists,
            "prepare_documentation": bank_tools.prepare_documentation,
            "generate_customer_response": response_generator.generate,
        },
        allowlists={
            "identity_agent": {"verify_identity"},
            "risk_agent": {"check_risk_lists"},
            "documentation_agent": {"prepare_documentation"},
            "response_agent": {"generate_customer_response"},
        },
    )
    orchestrator = OnboardingOrchestrator(
        IdentityAgent(registry, specialist_explainer),
        RiskAgent(registry, specialist_explainer),
        DocumentationAgent(registry, specialist_explainer),
        ResponseAgent(registry),
        orchestration_advisor,
        InMemoryHumanEscalation(),
        audit,
        InMemoryStateRepository(),
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
    )
    return ApplicationContainer(orchestrator, audit, resources)

