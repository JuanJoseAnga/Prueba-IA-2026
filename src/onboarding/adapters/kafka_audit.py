from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from typing import Any

from src.onboarding.domain.models import AuditEvent


def _json_default(value: Any) -> str:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"No se puede serializar {type(value).__name__}")


class KafkaAuditPublisher:
    """Publica trazabilidad y explicabilidad, ordenada por onboarding."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        *,
        client_id: str = "onboarding-orchestrator",
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._client_id = client_id
        self._producer: Any | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        try:
            from aiokafka import AIOKafkaProducer
        except ImportError as exc:
            raise RuntimeError(
                "Falta la dependencia aiokafka; instale el proyecto con sus dependencias"
            ) from exc

        producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            client_id=self._client_id,
            acks="all",
            enable_idempotence=True,
            value_serializer=lambda value: json.dumps(
                value, default=_json_default, ensure_ascii=False
            ).encode("utf-8"),
            key_serializer=lambda value: value.encode("utf-8"),
        )
        await producer.start()
        self._producer = producer

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, event: AuditEvent) -> None:
        if self._producer is None:
            raise RuntimeError("El productor Kafka no está iniciado")
        payload = {
            "schema_version": "1.0",
            "event_type": "onboarding.audit_event",
            **asdict(event),
        }
        await self._producer.send_and_wait(
            self._topic,
            key=event.onboarding_id,
            value=payload,
            headers=[("content-type", b"application/json")],
        )

