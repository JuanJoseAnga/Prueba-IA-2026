# Orquestador de onboarding — arquitectura hexagonal

Implementación de referencia en Python 3.11 + FastAPI. El dominio y el caso de uso no dependen de HTTP ni de proveedores externos; las integraciones mock están detrás de puertos reemplazables.

## Levantar todo con Docker

El entorno incluye la API, PostgreSQL con datos mock y Kafka:

```bash
docker compose up --build
```

Servicios disponibles:

- Chat de onboarding: `http://localhost:8000`
- API y Swagger: `http://localhost:8000/docs`
- PostgreSQL: disponible dentro de Docker como `postgres:5432`
- Kafka: `localhost:9092`

Comprobar el servicio:

```bash
curl http://localhost:8000/health
```

Consultar directamente los datos mock:

```bash
docker compose exec postgres psql -U onboarding -d onboarding -c "SELECT * FROM mock_identity_profiles;"
```

Detener los contenedores sin borrar los datos:

```bash
docker compose down
```

El esquema y los datos iniciales están en `docker/postgres/init.sql`. PostgreSQL ejecuta ese archivo al crear el volumen por primera vez.

### Activar Groq para el agente de respuesta

Copiar el archivo de ejemplo y colocar una clave real:

```bash
cp .env.example .env
```

```dotenv
GROQ_API_KEY=gsk_su_clave_real
GROQ_SPECIALIST_MODEL=openai/gpt-oss-20b
GROQ_ORCHESTRATOR_MODEL=openai/gpt-oss-120b
```

Después reconstruir la API:

```bash
docker compose up --build -d
```

El orquestador usa `openai/gpt-oss-120b` para evaluar los resultados y recomendar `continue` o `escalate`. Identidad, riesgo, documentación y respuesta usan `openai/gpt-oss-20b` para producir explicaciones o mensajes. Todos emplean el cliente asíncrono y acumulan el stream.

Las políticas deterministas tienen prioridad sobre el LLM: identidad no verificada, confianza menor a `0.8` y riesgo `medium/high` siempre escalan. Por minimización de datos, Groq no recibe nombre, documento ni coincidencias de riesgo. Si la clave no está configurada o Groq falla, se usan decisiones y textos locales; el onboarding sigue operando.

### Escenarios mock en PostgreSQL

| Documento | Nombre | Resultado |
|---|---|---|
| `1712345678` | Juan Perez | Aprobado |
| `1712345999` | Cualquier nombre | Confianza 0.65, escala a humano |
| `1712345000` | Cualquier nombre | Identidad no verificada, escala a humano |
| `0999999999` | Cualquier nombre | Riesgo alto, escala a humano |
| `0888888888` | Cualquier nombre | Riesgo medio/ambiguo, escala a humano |
| Cualquier documento | Nombre con `Riesgo Alto` | Riesgo alto |
| Cualquier documento | Nombre con `Riesgo Medio` | Riesgo medio |

## Flujo

```text
POST /api/v1/onboarding/start
              |
       OnboardingOrchestrator
          /          \
 IdentityAgent     RiskAgent        (paralelo)
 verify_identity   check_risk_lists
          \          /
        decisión / escalamiento
                 |
       DocumentationAgent           (secuencial)
       prepare_documentation
                 |
          ResponseAgent
```

- Identidad y listas de riesgo se ejecutan en paralelo.
- Se escala automáticamente si identidad falla, confianza `< 0.8`, riesgo `high` o riesgo `medium` (tratado como ambigüedad).
- El registro `ControlledToolRegistry` bloquea en runtime cualquier herramienta fuera de la allowlist del agente.
- Cada inicio, resultado, decisión, error y escalamiento se guarda como evento de auditoría.
- Cada evento también se publica en Kafka, usando `onboarding_id` como clave para mantener el orden por solicitud.
- El caso de uso impone `max_steps=10` y timeout global de 30 segundos.
- Los repositorios en memoria son mocks. En producción se implementan los mismos puertos con PostgreSQL/event store, APIs KYC/AML y una cola de revisión humana.

## Estructura

```text
src/onboarding/
├── domain/          # Entidades, estados y reglas sin dependencias externas
├── application/     # Orquestador, agentes, puertos y control de herramientas
├── adapters/        # Herramientas y persistencia mock (salida)
└── entrypoints/     # API FastAPI (entrada)
tests/               # Pruebas del flujo y de seguridad
```

La regla de dependencia apunta hacia adentro: `entrypoints/adapters -> application -> domain`.

## Ejecutar

```bash
python -m venv .venv
# PowerShell
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn src.onboarding.entrypoints.api:app --reload
```

La API espera Kafka en `localhost:9092`. Se puede cambiar mediante:

```powershell
$env:KAFKA_BOOTSTRAP_SERVERS = "kafka-1:9092,kafka-2:9092"
$env:KAFKA_AUDIT_TOPIC = "bank.onboarding.audit.v1"
uvicorn src.onboarding.entrypoints.api:app --reload
```

El tópico debe existir con la política de retención, replicación y control de acceso definida por el banco. El productor usa `acks=all` e idempotencia; si Kafka no está disponible al iniciar, la API falla de forma cerrada para evitar procesar solicitudes sin trazabilidad.

Ejemplo de evento publicado:

```json
{
  "schema_version": "1.0",
  "event_type": "onboarding.audit_event",
  "event_id": "4a67...",
  "onboarding_id": "ba71...",
  "step": 4,
  "actor": "orchestrator",
  "action": "verification_decision",
  "status": "decision",
  "details": {"outcome": "escalate", "reason": "Confianza de identidad insuficiente (0.65)"},
  "occurred_at": "2026-09-30T21:00:00+00:00"
}
```

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/v1/onboarding/start \
  -H "Content-Type: application/json" \
  -d '{"prospect_name":"Juan Perez","document_id":"1712345678","product":"cuenta_ahorros"}'
```

Casos especiales del mock en memoria usado por las pruebas unitarias:

- Documento terminado en `999`: confianza 0.65, escala.
- Documento terminado en `000`: identidad no verificada, escala.
- Nombre que contiene `Riesgo Alto`: riesgo alto, escala.
- Nombre que contiene `Riesgo Medio`: riesgo medio/ambiguo, escala.

Ejecutar pruebas:

```bash
pytest -q
```

## Endurecimiento para producción

Usar persistencia transaccional e idempotencia por solicitud, cifrado y enmascaramiento de PII en auditoría, autenticación/autorización del endpoint, reintentos con circuit breaker, métricas/trazas, colas durables para revisión humana y configuración externa de umbrales/allowlists. El mensaje al cliente no revela la lista de riesgo ni detalles internos.
