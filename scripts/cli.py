"""CLI principal del Generador de Parciales AI.

Uso:
    pip install -e .
    parciales --help
    parciales generate --session-id <uuid> --count 20
    parciales build-exam --session-id <uuid> --exam-code CALC1-2025-001 --subject "Cálculo I"
    parciales grade --image hoja.jpg --exam-code CALC1-2025-001
    parciales grade-batch --folder fotos/ --exam-code CALC1-2025-001
    parciales analytics --exam-id <uuid> --output reporte.csv
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

app = typer.Typer(
    name="parciales",
    help="Generador agéntico de exámenes universitarios con IA.",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

# ── Configuración de logging ──────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
)
logger.add(
    "logs/parciales.log",
    rotation="10 MB",
    retention="30 days",
    level="DEBUG",
)


# ── Comando: generate ─────────────────────────────────────────────────────────
@app.command()
def generate(
    session_id: str = typer.Option(..., "--session-id", "-s", help="UUID de la sesión activa"),
    count: int = typer.Option(20, "--count", "-n", help="Número de preguntas a generar"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Tema específico"),
    output_json: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Guardar preguntas en JSON (pre-inserción)"
    ),
):
    """Genera preguntas MCQ vía el agente generador y las guarda en Supabase."""
    logger.info(f"Generando {count} preguntas para session={session_id} topic={topic}")
    typer.echo(
        "\nEste comando debe ser invocado por el Agente de IA usando el prompt "
        "'generator_agent.md' + 'judge_agent.md'.\n"
        "Para generación directa, el agente ejecuta este flujo automáticamente.\n"
    )
    if output_json:
        typer.echo(f"Las preguntas aprobadas se guardarán en: {output_json}")


# ── Comando: build-exam ───────────────────────────────────────────────────────
@app.command("build-exam")
def build_exam(
    session_id: str = typer.Option(..., "--session-id", "-s", help="UUID de la sesión"),
    exam_code: str = typer.Option(..., "--exam-code", "-c", help="Código del examen (ej: CALC1-2025-001)"),
    subject: str = typer.Option(..., "--subject", help="Nombre de la materia"),
    instructor_id: str = typer.Option(..., "--instructor-id", help="UUID del instructor (auth.users)"),
    count: int = typer.Option(10, "--count", "-n", help="Número de preguntas"),
    versions: int = typer.Option(1, "--versions", "-v", help="Cantidad de versiones (Forma A, B, C…)"),
    output_dir: Path = typer.Option(
        Path("workspace/generated_exams"),
        "--output-dir",
        help="Directorio de salida",
    ),
    course_id: Optional[str] = typer.Option(None, "--course-id", help="UUID del curso (opcional)"),
):
    """Arma un examen barajado y genera los archivos .docx."""
    from scripts.compile_exam import build_exam_batch

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Armando {versions} versión(es) de {exam_code} con {count} preguntas")

    exam_ids = build_exam_batch(
        instructor_id=instructor_id,
        session_id=session_id,
        base_exam_code=exam_code,
        subject=subject,
        question_count=count,
        versions=versions,
        output_dir=output_dir,
        course_id=course_id,
    )

    typer.echo(f"\n✓ {len(exam_ids)} examen(es) generado(s) en {output_dir}")
    for eid in exam_ids:
        typer.echo(f"  exam_id={eid}")


# ── Comando: grade ────────────────────────────────────────────────────────────
@app.command()
def grade(
    image: Path = typer.Argument(..., help="Ruta a la imagen de la hoja de respuestas"),
    exam_code: Optional[str] = typer.Option(
        None, "--exam-code", help="Código del examen (si no hay QR legible)"
    ),
    student_id: Optional[str] = typer.Option(
        None, "--student-id", help="ID del estudiante (si no hay QR legible)"
    ),
    confidence_threshold: float = typer.Option(
        0.90, "--threshold", help="Umbral de confianza por celda (0–1)"
    ),
    save_debug: bool = typer.Option(False, "--debug", help="Guardar imagen de diagnóstico"),
):
    """Califica una hoja de respuestas usando el pipeline OMR híbrido."""
    from scripts.omr_pipeline import grade_sheet

    if not image.exists():
        typer.echo(f"Error: imagen no encontrada: {image}", err=True)
        raise typer.Exit(1)

    logger.info(f"Calificando: {image.name}")
    result = grade_sheet(
        image_path=image,
        fallback_exam_code=exam_code,
        fallback_student_id=student_id,
        confidence_threshold=confidence_threshold,
        save_debug=save_debug,
    )

    if result:
        typer.echo(f"\n✓ Estudiante : {result['student_id']}")
        typer.echo(f"  Examen     : {result['exam_code']}")
        typer.echo(f"  Nota       : {result['score']:.1f} / 5.0")
        typer.echo(f"  Correctas  : {result['correct_count']} / {result['total_count']}")
        typer.echo(f"  Confianza  : {result['vision_confidence_avg']:.1%}")
        if result.get("needs_review"):
            typer.echo("  ⚠ Requiere revisión manual")
    else:
        typer.echo("✗ No se pudo procesar la imagen.", err=True)
        raise typer.Exit(1)


# ── Comando: grade-batch ──────────────────────────────────────────────────────
@app.command("grade-batch")
def grade_batch(
    folder: Path = typer.Argument(..., help="Carpeta con imágenes JPG/PNG"),
    exam_code: Optional[str] = typer.Option(None, "--exam-code", help="Código del examen por defecto"),
    output_csv: Path = typer.Option(
        Path("workspace/generated_exams/calificaciones.csv"),
        "--output",
        help="CSV de salida",
    ),
    confidence_threshold: float = typer.Option(0.90, "--threshold"),
):
    """Califica todas las hojas de una carpeta y produce un CSV consolidado."""
    from scripts.omr_pipeline import grade_sheet

    if not folder.is_dir():
        typer.echo(f"Error: {folder} no es un directorio.", err=True)
        raise typer.Exit(1)

    images = sorted([*folder.glob("*.jpg"), *folder.glob("*.jpeg"), *folder.glob("*.png")])
    if not images:
        typer.echo("No se encontraron imágenes en la carpeta.", err=True)
        raise typer.Exit(1)

    import csv

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    processed = 0
    errors = 0

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["archivo", "student_id", "exam_code", "nota", "correctas",
                        "total", "confianza", "revision"],
        )
        writer.writeheader()

        for img in images:
            try:
                result = grade_sheet(
                    image_path=img,
                    fallback_exam_code=exam_code,
                    confidence_threshold=confidence_threshold,
                )
                if result:
                    writer.writerow({
                        "archivo": img.name,
                        "student_id": result["student_id"],
                        "exam_code": result["exam_code"],
                        "nota": f"{result['score']:.1f}",
                        "correctas": result["correct_count"],
                        "total": result["total_count"],
                        "confianza": f"{result['vision_confidence_avg']:.3f}",
                        "revision": "SI" if result.get("needs_review") else "NO",
                    })
                    processed += 1
                else:
                    errors += 1
                    writer.writerow({"archivo": img.name, "nota": "ERROR"})
            except Exception as exc:
                logger.error(f"Error procesando {img.name}: {exc}")
                errors += 1
                writer.writerow({"archivo": img.name, "nota": "ERROR"})

    typer.echo(f"\n✓ Procesadas: {processed}/{len(images)} imágenes")
    if errors:
        typer.echo(f"  ✗ Errores: {errors} (requieren revisión manual)")
    typer.echo(f"  CSV guardado en: {output_csv}")


# ── Comando: analytics ────────────────────────────────────────────────────────
@app.command()
def analytics(
    exam_id: str = typer.Argument(..., help="UUID del examen"),
    output: Path = typer.Option(
        Path("workspace/generated_exams/analytics.csv"),
        "--output",
        help="Ruta del CSV de salida",
    ),
    format: str = typer.Option("csv", "--format", help="Formato de salida: csv | json"),
):
    """Genera reporte de analítica pedagógica (p-value, bloom, dificultad por pregunta)."""
    from scripts.generate_analytics import generate_full_report

    output.parent.mkdir(parents=True, exist_ok=True)
    generate_full_report(exam_id=exam_id, output_path=output, fmt=format)
    typer.echo(f"\n✓ Reporte guardado en: {output}")


# ── Comando: setup-db ─────────────────────────────────────────────────────────
@app.command("setup-db")
def setup_db():
    """Imprime instrucciones para aplicar el schema en Supabase."""
    schema_path = Path(__file__).parent / "schema.sql"
    typer.echo("\nPara aplicar el schema en Supabase:")
    typer.echo("  1. Abre el SQL Editor en tu proyecto de Supabase.")
    typer.echo(f"  2. Copia el contenido de: {schema_path.resolve()}")
    typer.echo("  3. Ejecuta el script completo.\n")
    typer.echo("Alternativa con CLI de Supabase:")
    typer.echo("  supabase db push\n")


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app()
