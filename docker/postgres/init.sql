CREATE TABLE IF NOT EXISTS mock_identity_profiles (
    document_id VARCHAR(30) PRIMARY KEY,
    verified BOOLEAN NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    scenario VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS mock_risk_profiles (
    id BIGSERIAL PRIMARY KEY,
    document_id VARCHAR(30) NOT NULL DEFAULT '',
    name_pattern VARCHAR(120) NOT NULL DEFAULT '',
    risk_level VARCHAR(10) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    matches JSONB NOT NULL DEFAULT '[]'::jsonb,
    scenario VARCHAR(100) NOT NULL,
    UNIQUE (document_id, name_pattern)
);

CREATE INDEX IF NOT EXISTS idx_mock_risk_document_id
    ON mock_risk_profiles (document_id);

CREATE TABLE IF NOT EXISTS mock_product_documents (
    product VARCHAR(50) NOT NULL,
    document_name VARCHAR(100) NOT NULL,
    display_order SMALLINT NOT NULL,
    PRIMARY KEY (product, document_name)
);

INSERT INTO mock_identity_profiles (document_id, verified, confidence, scenario) VALUES
    ('1712345678', TRUE, 0.960, 'flujo aprobado'),
    ('1712345999', TRUE, 0.650, 'confianza ambigua'),
    ('1712345000', FALSE, 0.950, 'identidad rechazada')
ON CONFLICT (document_id) DO UPDATE SET
    verified = EXCLUDED.verified,
    confidence = EXCLUDED.confidence,
    scenario = EXCLUDED.scenario;

INSERT INTO mock_risk_profiles (document_id, name_pattern, risk_level, matches, scenario) VALUES
    ('0999999999', 'Riesgo Alto', 'high', '["MOCK-LIST-001"]', 'coincidencia de riesgo alto'),
    ('0888888888', 'Riesgo Medio', 'medium', '["MOCK-REVIEW-001"]', 'coincidencia ambigua')
ON CONFLICT (document_id, name_pattern) DO UPDATE SET
    risk_level = EXCLUDED.risk_level,
    matches = EXCLUDED.matches,
    scenario = EXCLUDED.scenario;

INSERT INTO mock_product_documents (product, document_name, display_order) VALUES
    ('cuenta_ahorros', 'contrato_cuenta', 1),
    ('cuenta_ahorros', 'declaracion_origen_fondos', 2),
    ('cuenta_ahorros', 'tratamiento_datos', 3),
    ('cuenta_corriente', 'contrato_cuenta', 1),
    ('cuenta_corriente', 'declaracion_origen_fondos', 2),
    ('cuenta_corriente', 'tratamiento_datos', 3),
    ('cuenta_corriente', 'referencias', 4)
ON CONFLICT (product, document_name) DO UPDATE SET
    display_order = EXCLUDED.display_order;
