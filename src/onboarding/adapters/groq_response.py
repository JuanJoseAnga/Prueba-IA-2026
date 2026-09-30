from __future__ import annotations

import json
from typing import Any

from src.onboarding.application.ports import CustomerResponseGenerator
from src.onboarding.domain.models import (
    IdentityResult,
    OrchestrationAdvice,
    Prospect,
    RiskResult,
)


class GroqResponseGenerator:
    """Genera el mensaje al cliente sin enviar documento ni detalles AML al LLM."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "openai/gpt-oss-20b",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client: Any | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        try:
            from groq import AsyncGroq
        except ImportError as exc:
            raise RuntimeError("Falta la dependencia groq") from exc
        self._client = AsyncGroq(
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            max_retries=1,
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def generate(
        self, prospect: Prospect, approved: bool, reason: str | None
    ) -> str:
        if self._client is None:
            raise RuntimeError("El cliente Groq no está iniciado")

        # Minimización de datos: nunca se envía document_id, matches ni la causa AML.
        context = {
            "product": prospect.product,
            "outcome": "approved" if approved else "manual_review",
        }
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres el agente de comunicación de un banco. Redacta en español "
                        "un mensaje final, claro, empático y de máximo 60 palabras. "
                        "Responde únicamente con el mensaje para el cliente. No inventes "
                        "plazos, requisitos ni aprobaciones. No menciones listas de riesgo, "
                        "puntajes, modelos, agentes, sistemas internos o razonamiento. Si el "
                        "resultado es manual_review, indica que un especialista revisará la "
                        "solicitud y que no es necesario enviarla de nuevo."
                    ),
                },
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_completion_tokens=256,
            top_p=0.95,
            reasoning_effort="medium",
            include_reasoning=False,
            stream=True,
            stop=None,
        )

        parts: list[str] = []
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                parts.append(content)
        message = "".join(parts).strip()
        if not message:
            raise RuntimeError("Groq devolvió una respuesta vacía")
        return message


class FallbackResponseGenerator:
    """Impide que una falla del LLM interrumpa una decisión de onboarding."""

    def __init__(
        self,
        primary: CustomerResponseGenerator,
        fallback: CustomerResponseGenerator,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    async def generate(
        self, prospect: Prospect, approved: bool, reason: str | None
    ) -> str:
        try:
            return await self._primary.generate(prospect, approved, reason)
        except Exception:
            return await self._fallback.generate(prospect, approved, reason)


class GroqSpecialistExplainer(GroqResponseGenerator):
    async def explain(self, specialty: str, context: dict[str, Any]) -> str:
        if self._client is None:
            raise RuntimeError("El cliente Groq no está iniciado")
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un agente bancario especializado. Explica el resultado en "
                        "español, en máximo 35 palabras, usando solo los datos suministrados. "
                        "No incluyas razonamiento interno, recomendaciones ni datos personales."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"specialty": specialty, "result": context}, ensure_ascii=False
                    ),
                },
            ],
            temperature=0.2,
            max_completion_tokens=160,
            top_p=0.9,
            reasoning_effort="medium",
            include_reasoning=False,
            stream=True,
            stop=None,
        )
        parts: list[str] = []
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                parts.append(content)
        explanation = "".join(parts).strip()
        if not explanation:
            raise RuntimeError("Groq devolvió una explicación vacía")
        return explanation


class GroqOrchestrationAdvisor(GroqResponseGenerator):
    async def advise(
        self, identity: IdentityResult, risk: RiskResult
    ) -> OrchestrationAdvice:
        if self._client is None:
            raise RuntimeError("El cliente Groq no está iniciado")
        context = {
            "identity": {
                "verified": identity.verified,
                "confidence": identity.confidence,
            },
            "risk": {
                "level": risk.risk_level,
                "match_count": len(risk.matches),
            },
            "policy": {
                "identity_must_be_verified": True,
                "minimum_identity_confidence": 0.8,
                "manual_review_risk_levels": ["medium", "high"],
            },
        }
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres el agente orquestador de onboarding bancario. Evalúa únicamente "
                        "el JSON recibido. Responde JSON válido sin markdown con las claves "
                        "decision (continue o escalate) y explanation (máximo 40 palabras). "
                        "Ante ambigüedad elige escalate. No incluyas razonamiento interno."
                    ),
                },
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_completion_tokens=200,
            top_p=0.9,
            reasoning_effort="medium",
            include_reasoning=False,
            stream=True,
            stop=None,
        )
        parts: list[str] = []
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                parts.append(content)
        raw = "".join(parts).strip()
        data = json.loads(raw)
        decision = data.get("decision")
        explanation = data.get("explanation")
        if decision not in {"continue", "escalate"} or not isinstance(explanation, str):
            raise ValueError("Respuesta inválida del agente orquestador")
        return OrchestrationAdvice(decision=decision, explanation=explanation)


class FallbackSpecialistExplainer:
    def __init__(self, primary: Any, fallback: Any) -> None:
        self._primary = primary
        self._fallback = fallback

    async def explain(self, specialty: str, context: dict[str, Any]) -> str:
        try:
            return await self._primary.explain(specialty, context)
        except Exception:
            return await self._fallback.explain(specialty, context)


class FallbackOrchestrationAdvisor:
    def __init__(self, primary: Any, fallback: Any) -> None:
        self._primary = primary
        self._fallback = fallback

    async def advise(
        self, identity: IdentityResult, risk: RiskResult
    ) -> OrchestrationAdvice:
        try:
            return await self._primary.advise(identity, risk)
        except Exception:
            return await self._fallback.advise(identity, risk)

