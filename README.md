# Generador de Parciales - Agentic Workflow

Este repositorio contiene la estructura de herramientas y prompts para un sistema de gestión de parciales universitarios operado por Agentes de IA.

## Estructura

- `prompts/`: Instrucciones maestras para los agentes (Generador, Juez, Calificador).
- `scripts/`: Scripts utilitarios en Python para interactuar con Supabase y compilar documentos.
- `templates/`: Plantillas académicas para la generación de exámenes en PDF/Word.
- `workspace/`: Espacio de trabajo para material de origen y exámenes generados.

## Requisitos

1. **Supabase**: Base de datos configurada para almacenar preguntas y claves de respuestas.
2. **NotebookLM**: Para el procesamiento de libros de texto académicos (RAG).
3. **Pandoc**: Para la compilación de exámenes profesionales.
