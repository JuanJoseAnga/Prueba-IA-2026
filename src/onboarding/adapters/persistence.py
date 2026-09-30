from __future__ import annotations

import asyncio
from typing import Protocol

from src.onboarding.domain.models import AuditEvent, OnboardingState


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = asyncio.Lock()

    async def append(self, event: AuditEvent) -> None:
        async with self._lock:
            self._events.append(event)

    async def list_for(self, onboarding_id: str) -> list[AuditEvent]:
        return [event for event in self._events if event.onboarding_id == onboarding_id]


class AuditEventPublisher(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def publish(self, event: AuditEvent) -> None: ...


class PublishingAuditRepository:
    """Persiste para consulta y publica el mismo evento a sinks externos."""

    def __init__(
        self,
        repository: InMemoryAuditRepository,
        publishers: list[AuditEventPublisher] | None = None,
    ) -> None:
        self._repository = repository
        self._publishers = publishers or []
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        for publisher in self._publishers:
            await publisher.start()

    async def stop(self) -> None:
        for publisher in reversed(self._publishers):
            await publisher.stop()

    async def append(self, event: AuditEvent) -> None:
        # El lock conserva el orden de eventos tanto localmente como en Kafka.
        async with self._lock:
            await self._repository.append(event)
            for publisher in self._publishers:
                await publisher.publish(event)

    async def list_for(self, onboarding_id: str) -> list[AuditEvent]:
        return await self._repository.list_for(onboarding_id)


class InMemoryStateRepository:
    def __init__(self) -> None:
        self._states: dict[str, OnboardingState] = {}

    async def save(self, state: OnboardingState) -> None:
        self._states[state.onboarding_id] = state

    async def get(self, onboarding_id: str) -> OnboardingState | None:
        return self._states.get(onboarding_id)

