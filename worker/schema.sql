-- CuchiFijas · avisos públicos: suscripciones Web Push y avisos ya enviados, en D1.
-- Idempotente: se puede aplicar varias veces sin perder datos.
-- No se guarda IP, user agent ni nada personal: solo lo necesario para enviar el push.

CREATE TABLE IF NOT EXISTS suscripciones (
  id          TEXT PRIMARY KEY,   -- SHA-256 del endpoint (normalizado), en hex
  endpoint    TEXT NOT NULL,      -- URL del servicio push (allowlist del Worker)
  p256dh      TEXT NOT NULL,      -- llave pública del navegador, base64url (65 bytes)
  auth        TEXT NOT NULL,      -- secreto de autenticación, base64url (16 bytes)
  creado      TEXT NOT NULL,      -- ISO 8601 UTC
  actualizado TEXT NOT NULL       -- ISO 8601 UTC; solo cambia cuando cambian las llaves
);

-- Contador mantenido por triggers: el tope se revisa leyendo una fila, no contando toda la tabla
-- (D1 cobra por filas leídas). Si la fila falta, el Worker lo trata como lleno.
CREATE TABLE IF NOT EXISTS contadores (
  nombre TEXT PRIMARY KEY,
  valor  INTEGER NOT NULL
);

INSERT OR IGNORE INTO contadores (nombre, valor)
  SELECT 'suscripciones', COUNT(*) FROM suscripciones;

CREATE TRIGGER IF NOT EXISTS suscripciones_alta AFTER INSERT ON suscripciones
BEGIN
  UPDATE contadores SET valor = valor + 1 WHERE nombre = 'suscripciones';
END;

CREATE TRIGGER IF NOT EXISTS suscripciones_baja AFTER DELETE ON suscripciones
BEGIN
  UPDATE contadores SET valor = valor - 1 WHERE nombre = 'suscripciones';
END;

-- Avisos ya enviados ("<id_partido>@<inicio UTC>"): el workflow marca antes de enviar, así cada
-- aviso sale como máximo una vez aunque haya corridas repetidas. /v1/marcar borra lo de más de 3 días.
CREATE TABLE IF NOT EXISTS enviados (
  clave  TEXT PRIMARY KEY,
  creado INTEGER NOT NULL         -- epoch en milisegundos
);
