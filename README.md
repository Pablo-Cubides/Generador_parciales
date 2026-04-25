# 🎓 Generador de Parciales AI — Agentic Workflow v2

Un sistema profesional de grado ingeniería para la gestión, generación y calificación de exámenes universitarios, diseñado para ser operado por **Agentes de IA** (Claude Code, Anthropic API).

Este proyecto es un **ecosistema de trabajo agéntico**: el Agente de IA actúa como orquestador y el repositorio le proporciona las herramientas (scripts Python), el cerebro (prompts), la memoria (Supabase) y el pipeline de calificación (OMR híbrido).

---

## 🚀 Arquitectura Agéntica

```mermaid
graph TD
    User((Instructor)) -->|Instrucción| Agent[Agente de IA]
    Agent -->|RAG via MCP| NotebookLM[NotebookLM / Docs]
    NotebookLM -->|Chunk + Cita| Agent
    Agent -->|Fase 1: Draft| Gen[generator_agent.md]
    Gen -->|Borradores JSON| Judge[judge_agent.md]
    Judge -->|Aprobadas| DB[(Supabase + pgvector)]
    Agent -->|build-exam CLI| Script[compile_exam.py]
    Script -->|QR + Marcadores OMR| Docx[Word / PDF]
    User -->|Sube foto| Agent
    Agent -->|Pasada A: OpenCV| OMR[omr_pipeline.py]
    OMR -->|Baja confianza| Vision[grader_agent.md Vision LLM]
    Vision -->|Reconciliación| OMR
    OMR -->|responses granulares| DB
    DB -->|item analysis| Analyst[analyst_agent.md]
    Analyst -->|Recomendaciones| User
```

---

## ✨ Características Principales

| Módulo | Descripción |
|---|---|
| **📖 RAG Académico** | Ingesta de libros vía NotebookLM MCP; cita obligatoria de fuente, página y extracto |
| **🧠 Pipeline 3 fases** | Draft → Judge (rúbrica binaria 5 criterios) → Inserción solo de aprobadas |
| **🔀 Anti-fraude** | Permutación de opciones + orden de preguntas; N versiones (Forma A/B/C…) |
| **📄 Documentos OMR** | `.docx` con QR (exam_code\|form\|n), marcadores de esquina ■ y tabla de burbujas Unicode |
| **👁️ OMR Híbrido** | Pasada A OpenCV (determinista) + Pasada B LLM Vision (solo celdas < 90% confianza) |
| **📊 Analítica** | p-valor real por pregunta, distribución Bloom, alertas automáticas, recomendaciones del Analyst Agent |
| **🔒 Seguridad** | RLS en todas las tablas, student_id pseudonimizado (sha256+pepper), sin anon access a claves |

---

## 📁 Estructura del Proyecto

```
.
├── pyproject.toml               # Dependencias pinneadas, CLI entry point
├── prompts/
│   ├── generator_agent.md       # Pipeline 3 fases (RAG → Draft → Judge)
│   ├── judge_agent.md           # Rúbrica binaria de calidad
│   ├── grader_agent.md          # Visión LLM (fallback OMR)
│   └── analyst_agent.md        # Analítica pedagógica e interpretación
├── scripts/
│   ├── schema.sql               # Schema v2: RLS, pgvector, índices, enums
│   ├── supabase_client.py       # Cliente centralizado con pseudonimización
│   ├── compile_exam.py          # Barajado + QR + marcadores + batch
│   ├── generate_analytics.py    # Analítica real desde tabla responses
│   ├── omr_pipeline.py          # OMR híbrido OpenCV + LLM
│   └── cli.py                   # CLI Typer (parciales build-exam, grade, analytics…)
├── templates/                   # Plantillas .docx base (a crear según necesidad)
└── workspace/
    ├── raw_material/            # Material académico fuente (ignorado en git)
    └── generated_exams/         # Exámenes y reportes generados (ignorado en git)
```

---

## 🛠 Configuración Inicial

### 1. Requisitos
- **Python 3.11+**
- **Cuenta Supabase** (tier gratuito funciona)
- **Anthropic API Key** (para LLM fallback en OMR)

### 2. Instalación

```bash
# Clonar el repo
git clone https://github.com/tu-usuario/generador-parciales.git
cd generador-parciales

# Instalar en modo editable
pip install -e .

# Verificar CLI
parciales --help
```

### 3. Variables de entorno

Crea `.env` basado en `.env.example`:

```env
# Supabase
SUPABASE_URL=https://[PROJECT_ID].supabase.co
SUPABASE_KEY=tu_anon_public_key
SUPABASE_SERVICE_ROLE=tu_service_role_key   # solo para scripts de admin

# Pepper para pseudonimización de student_id
STUDENT_PEPPER=cadena-aleatoria-secreta-larga

# Anthropic (para fallback LLM en OMR)
ANTHROPIC_API_KEY=sk-ant-...

# Base de datos directa (opcional, para psql/migraciones)
DATABASE_URL=postgresql://postgres.[PROJECT_ID]:[PASSWORD]@aws-1-us-east-1.pooler.supabase.com:5432/postgres
```

### 4. Aplicar el Schema de Base de Datos

Ejecuta `scripts/schema.sql` en el **SQL Editor** de tu proyecto Supabase, o:

```bash
parciales setup-db   # muestra las instrucciones
```

El schema incluye: extensión `pgvector`, tablas con RLS habilitado, índices en FK, enums, y funciones de análisis de ítems.

---

## 🤖 Flujos de Uso (Guía para el Agente)

### Paso 1 — Crear sesión y generar banco de preguntas

```
"Usa el prompt generator_agent.md. Crea una sesión para la materia 'Cálculo I',
tema 'Derivadas de funciones trascendentes'. Conecta con NotebookLM y genera
25 preguntas. Aplica el judge_agent.md a cada una y guarda solo las aprobadas."
```

### Paso 2 — Armar examen(es)

```bash
# Via CLI (una sola versión)
parciales build-exam \
  --session-id <uuid> \
  --exam-code CALC1-2025-001 \
  --subject "Cálculo I" \
  --instructor-id <uuid> \
  --count 15 \
  --versions 3          # genera Formas A, B y C

# Resultado: workspace/generated_exams/CALC1-2025-001-A.docx (etc.)
```

### Paso 3 — Calificar hojas de respuestas

```bash
# Una hoja
parciales grade hoja_juan.jpg --exam-code CALC1-2025-001

# Lote completo
parciales grade-batch fotos_parcial/ --exam-code CALC1-2025-001

# Resultado: calificaciones.csv con notas y flag de revisión manual
```

### Paso 4 — Analítica pedagógica

```bash
parciales analytics <exam_id> --output workspace/generated_exams/analytics.csv
```

Luego comparte el CSV con el agente:
```
"Usa analyst_agent.md para interpretar este reporte y dame recomendaciones."
```

---

## 🧪 Tests y Calidad

```bash
# Linting
pip install -e ".[dev]"
ruff check scripts/
mypy scripts/

# Tests (en construcción)
pytest
```

---

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).

**Desarrollado con Claude Code (Anthropic).**
