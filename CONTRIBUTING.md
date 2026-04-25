# Guía de Contribución

## Configuración del entorno de desarrollo

```bash
git clone https://github.com/tu-usuario/generador-parciales.git
cd generador-parciales
pip install -e ".[dev]"
cp .env.example .env
# Edita .env con tus credenciales de Supabase
```

## Estilo de código

- **Formatter/Linter:** `ruff` — ejecuta `ruff check scripts/ && ruff format scripts/`
- **Tipos:** `mypy scripts/` para verificar anotaciones
- **Python:** 3.11+ requerido

## Tests

```bash
pytest                     # todos los tests
pytest -k test_analytics   # tests específicos
pytest --cov=scripts       # con cobertura
```

Para añadir tests: crea archivos en `tests/` con el prefijo `test_`.

## Flujo de contribución

1. Crea un branch descriptivo: `git checkout -b feat/omr-aruco-markers`
2. Haz tus cambios con commits atómicos.
3. Verifica que `ruff check` y `pytest` pasen sin errores.
4. Abre un Pull Request describiendo el problema que resuelve y cómo probarlo.

## Convenciones de commits

```
feat: añadir soporte de marcadores ArUco para OMR
fix: corregir cálculo de confianza en celdas vacías
refactor: extraer lógica de QR a helper separado
docs: actualizar guía de configuración
test: añadir tests para compile_exam batch generation
```

## Reportar bugs

Incluye:
- Versión de Python (`python --version`)
- Sistema operativo
- Pasos para reproducir el error
- Stacktrace completo

## Privacidad y seguridad

- **Nunca** subas archivos `.env`, imágenes de hojas de respuestas reales, o datos de estudiantes.
- **Nunca** expongas `SUPABASE_SERVICE_ROLE` o `ANTHROPIC_API_KEY` en código o commits.
- Las imágenes de test deben ser sintéticas (sin nombres ni códigos reales).

## Schema de base de datos

Si modificas `scripts/schema.sql`, asegúrate de:
1. Usar `IF NOT EXISTS` y `DO $$ ... EXCEPTION WHEN duplicate_object` para idempotencia.
2. Añadir índices a todas las FK nuevas.
3. Habilitar RLS en tablas nuevas y definir sus políticas.
4. Documentar el propósito de cada tabla/columna con un comentario SQL.
