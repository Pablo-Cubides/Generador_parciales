# 🎓 Generador de Parciales AI - Agentic Workflow

Un sistema profesional de grado ingeniería para la gestión, generación y calificación de exámenes universitarios, diseñado para ser operado por **Agentes de IA** (como Antigravity, Claude Code o OpenClaw).

Este proyecto no es una simple aplicación; es un **ecosistema de trabajo agéntico** que utiliza IA para procesar libros de texto, generar bancos de preguntas técnicos, armar exámenes únicos con permutación de opciones y calificar automáticamente mediante visión artificial.

---

## 🚀 La Visión: Flujo Agéntico

A diferencia de un backend tradicional, aquí el **Agente de IA es el orquestador**. El repositorio proporciona las herramientas (scripts), el cerebro (prompts) y la memoria (Supabase) para que el agente ejecute tareas complejas bajo tu demanda.

```mermaid
graph TD
    User((Usuario)) -->|Instrucción| Agent[Agente de IA]
    Agent -->|RAG| NotebookLM[NotebookLM MCP]
    NotebookLM -->|Extracto Académico| Agent
    Agent -->|Generar Preguntas| DB[(Supabase)]
    Agent -->|Permutar y Compilar| Script[Python Scripts]
    Script -->|Generar| Docx[Word / PDF]
    User -->|Sube Foto| Agent
    Agent -->|Visión| Grader[Agente Calificador]
    Grader -->|Valida contra DB| DB
    Grader -->|Nota Final| User
```

---

## ✨ Características Principales

- **📖 RAG Académico (NotebookLM):** Ingesta de libros de texto, guías y sílabos mediante el protocolo MCP para asegurar rigor técnico y fidelidad al material de clase.
- **🧠 Generación Inteligente (A-E):** Creación de preguntas de selección múltiple con 5 opciones (1 correcta + 4 distractores lógicos) evitando errores comunes.
- **🔀 Permutación de Opciones (Unicidad):** Capacidad de generar múltiples versiones del mismo examen donde el orden de las opciones cambia, manteniendo una "Answer Key" única en base de datos para cada parcial.
- **📄 Documentos Profesionales:** Generación de archivos `.docx` (Word) optimizados con membrete universitario, tabla de respuestas y formato listo para imprimir.
- **👁️ Calificación por Visión:** Procesamiento de fotos de hojas de respuestas; el agente identifica al estudiante y califica comparando con la base de datos de Supabase.

---

## 📁 Estructura del Proyecto

- `prompts/`: El "cerebro" del sistema. Contiene las reglas maestras para que los agentes no alucinen y mantengan el rigor académico.
- `scripts/`: El "músculo" del sistema. Scripts en Python para conexión a base de datos y manipulación de documentos.
- `templates/`: Plantillas visuales para asegurar que los exámenes se vean impecables.
- `workspace/`: Tu área de trabajo local para material de origen y resultados.

---

## 🛠 Configuración Inicial

### 1. Requisitos Previos
- **Python 3.11+**
- **Supabase Account** (Crea un proyecto gratuito).
- **GitHub CLI (gh)** configurado.

### 2. Instalación de Dependencias
```bash
pip install supabase python-dotenv python-docx
```

### 3. Base de Datos (Supabase)
Ejecuta el script SQL ubicado en `scripts/schema.sql` dentro del **SQL Editor** de tu panel de Supabase.

**Detalles de conexión:**
- **Host:** `db.wuyndjgycejlcpotgwzx.supabase.co`
- **Database:** `postgres`
- **User:** `postgres`

### 4. Variables de Env (Agent Skills)
He instalado los `supabase/agent-skills` para mejorar la precisión. Si cambias de entorno, puedes ejecutar:
```bash
npx skills add supabase/agent-skills -y
```

### 5. Variables de Entorno
Crea un archivo `.env` en la raíz basado en `.env.example`:
```env
SUPABASE_URL=https://wuyndjgycejlcpotgwzx.supabase.co
SUPABASE_KEY=tu_anon_public_key
# Connection string para scripts directos
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.wuyndjgycejlcpotgwzx.supabase.co:5432/postgres
```

---

## 🤖 Cómo Operar el Sistema (Guía para el Usuario)

Para usar este sistema, simplemente dale instrucciones al Agente de IA dentro de este entorno:

### Paso 1: Generar Banco de Preguntas
> *"Usa el prompt `generator_agent.md` para leer el libro [Título] en NotebookLM y genérame 30 preguntas sobre el tema de Derivadas. Guárdalas en Supabase."*

### Paso 2: Crear un Examen Físico
> *"Selecciona 10 preguntas del banco de Supabase y ármame un examen para la materia 'Cálculo I'. Genera el archivo Word en la carpeta de workspace."*

### Paso 3: Calificar Parciales
> (Sube una foto de un examen resuelto)
> *"Usa el `grader_agent.md` para calificar esta foto buscando el ID del estudiante y comparando sus respuestas con la clave en Supabase."*

---

## 📄 Licencia
Este proyecto es de uso privado/académico. El repositorio es público temporalmente para desarrollo colaborativo.

---
**Desarrollado con Antigravity AI.**
