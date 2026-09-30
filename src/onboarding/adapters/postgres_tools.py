from __future__ import annotations

import json
from typing import Any

from src.onboarding.domain.models import DocumentationResult, IdentityResult, RiskResult


class PostgresBankTools:
    """Herramientas mock cuyos resultados se administran como datos en PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: Any | None = None

    async def start(self) -> None:
        if self._pool is not None:
            return
        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError("Falta la dependencia asyncpg") from exc
        self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)

    async def stop(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> Any:
        if self._pool is None:
            raise RuntimeError("El pool PostgreSQL no está iniciado")
        return self._pool

    async def verify_identity(self, document_id: str) -> IdentityResult:
        row = await self._require_pool().fetchrow(
            """
            SELECT verified, confidence
            FROM mock_identity_profiles
            WHERE document_id = $1
            """,
            document_id,
        )
        if row is None:
            return IdentityResult(verified=True, confidence=0.96)
        return IdentityResult(verified=row["verified"], confidence=float(row["confidence"]))

    async def check_risk_lists(self, name: str, document_id: str) -> RiskResult:
        row = await self._require_pool().fetchrow(
            """
            SELECT risk_level, matches
            FROM mock_risk_profiles
            WHERE document_id = $1
               OR ($2 ILIKE '%' || name_pattern || '%')
            ORDER BY CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
            LIMIT 1
            """,
            document_id,
            name,
        )
        if row is None:
            return RiskResult(risk_level="low", matches=[])
        matches = row["matches"]
        if isinstance(matches, str):
            matches = json.loads(matches)
        return RiskResult(risk_level=row["risk_level"], matches=list(matches))

    async def prepare_documentation(
        self, product: str, client_data: dict[str, str]
    ) -> DocumentationResult:
        rows = await self._require_pool().fetch(
            """
            SELECT document_name
            FROM mock_product_documents
            WHERE product = $1
            ORDER BY display_order
            """,
            product,
        )
        documents = [row["document_name"] for row in rows]
        if not documents:
            documents = ["formulario_producto", "tratamiento_datos"]
        return DocumentationResult(required_documents=documents)

