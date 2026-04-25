"""Generación de reportes de analítica pedagógica.

Produce un CSV o JSON con:
  - p-value por pregunta (tasa de aciertos real desde la tabla responses)
  - Distribución por nivel de Bloom
  - Distribución por dificultad
  - Preguntas que necesitan revisión (p < 0.2 o p > 0.9)
  - Resumen general del examen
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from loguru import logger

from scripts.supabase_client import (
    compute_item_analysis,
    get_grades_by_exam,
    supabase,
)


def _fetch_exam_metadata(exam_id: str) -> dict[str, Any]:
    result = supabase.table("exams").select("*").eq("id", exam_id).execute()
    return result.data[0] if result.data else {}


def _fetch_response_distribution(exam_id: str) -> dict[str, dict[str, int]]:
    """Retorna distribución de marcas por pregunta: {answer_key_id: {A:n, B:n, ...}}."""
    result = (
        supabase.table("responses")
        .select("answer_key_id, marked_letter, is_correct")
        .in_(
            "answer_key_id",
            [
                ak["id"]
                for ak in supabase.table("answer_keys")
                .select("id")
                .eq("exam_id", exam_id)
                .execute()
                .data
            ],
        )
        .execute()
    )
    dist: dict[str, dict[str, int]] = {}
    for row in result.data:
        ak_id = row["answer_key_id"]
        letter = row.get("marked_letter") or "?"
        dist.setdefault(ak_id, {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "?": 0})
        dist[ak_id][letter] = dist[ak_id].get(letter, 0) + 1
    return dist


def generate_full_report(
    exam_id: str,
    output_path: Path | str,
    fmt: str = "csv",
) -> None:
    """Genera el reporte completo de analítica para un examen."""
    output_path = Path(output_path)
    exam_meta = _fetch_exam_metadata(exam_id)

    if not exam_meta:
        logger.error(f"Examen no encontrado: {exam_id}")
        return

    exam_code = exam_meta.get("exam_code", exam_id)
    subject = exam_meta.get("subject", "—")

    # ── Datos de item analysis desde la función SQL ───────────────────────
    items = compute_item_analysis(exam_id)

    if not items:
        logger.warning(f"Sin respuestas registradas para exam_id={exam_id}")
        logger.info("Asegúrate de haber ejecutado 'parciales grade-batch' primero.")
        return

    grades = get_grades_by_exam(exam_id)
    scores = [g["score"] for g in grades if g.get("score") is not None]

    avg_score = sum(scores) / len(scores) if scores else 0.0
    pass_count = sum(1 for s in scores if s >= 3.0)
    pass_rate = pass_count / len(scores) if scores else 0.0

    # ── Estadísticas por bloom y dificultad ──────────────────────────────
    bloom_stats: dict[str, dict[str, float]] = {}
    difficulty_stats: dict[str, dict[str, float]] = {}

    for item in items:
        bloom = item.get("bloom") or "sin_nivel"
        diff = item.get("difficulty") or "sin_nivel"
        pv = float(item.get("p_value") or 0)

        bloom_stats.setdefault(bloom, {"count": 0, "p_value_sum": 0.0})
        bloom_stats[bloom]["count"] += 1
        bloom_stats[bloom]["p_value_sum"] += pv

        difficulty_stats.setdefault(diff, {"count": 0, "p_value_sum": 0.0})
        difficulty_stats[diff]["count"] += 1
        difficulty_stats[diff]["p_value_sum"] += pv

    # Preguntas problemáticas (demasiado fáciles o demasiado difíciles)
    too_easy = [i for i in items if float(i.get("p_value") or 0) > 0.9]
    too_hard = [i for i in items if float(i.get("p_value") or 0) < 0.2]

    # ── Generación del reporte ────────────────────────────────────────────
    if fmt == "json":
        report = {
            "exam_code": exam_code,
            "subject": subject,
            "total_students": len(scores),
            "average_score": round(avg_score, 2),
            "pass_rate": round(pass_rate, 3),
            "items": [
                {
                    "question_id": i["question_id"],
                    "question_text": i["question_text"][:80] + "…",
                    "p_value": float(i.get("p_value") or 0),
                    "total_responses": i["total_responses"],
                    "correct_responses": i["correct_responses"],
                    "bloom": i.get("bloom"),
                    "difficulty": i.get("difficulty"),
                    "flag": (
                        "muy_facil" if float(i.get("p_value") or 0) > 0.9
                        else "muy_dificil" if float(i.get("p_value") or 0) < 0.2
                        else "ok"
                    ),
                }
                for i in items
            ],
            "bloom_summary": {
                k: {
                    "count": v["count"],
                    "avg_p_value": round(v["p_value_sum"] / v["count"], 3),
                }
                for k, v in bloom_stats.items()
            },
            "difficulty_summary": {
                k: {
                    "count": v["count"],
                    "avg_p_value": round(v["p_value_sum"] / v["count"], 3),
                }
                for k, v in difficulty_stats.items()
            },
            "flags": {
                "too_easy": len(too_easy),
                "too_hard": len(too_hard),
                "needs_revision": len(too_easy) + len(too_hard),
            },
        }
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    else:  # csv (default)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Encabezado del examen
            writer.writerow(["# Reporte de Analítica Pedagógica"])
            writer.writerow(["Examen", exam_code, "Materia", subject])
            writer.writerow(["Total estudiantes", len(scores)])
            writer.writerow(["Nota promedio", f"{avg_score:.2f}"])
            writer.writerow(["Tasa de aprobación", f"{pass_rate:.1%}"])
            writer.writerow([])

            # Detalle por pregunta
            writer.writerow([
                "N°", "Pregunta (extracto)", "p-valor", "Correctas",
                "Total", "Bloom", "Dificultad", "Alerta"
            ])

            for idx, item in enumerate(items, 1):
                pv = float(item.get("p_value") or 0)
                flag = ""
                if pv > 0.9:
                    flag = "⚠ Muy fácil (revisar)"
                elif pv < 0.2:
                    flag = "⚠ Muy difícil (revisar)"

                writer.writerow([
                    idx,
                    (item["question_text"][:60] + "…") if len(item["question_text"]) > 60 else item["question_text"],
                    f"{pv:.3f}",
                    item["correct_responses"],
                    item["total_responses"],
                    item.get("bloom") or "—",
                    item.get("difficulty") or "—",
                    flag,
                ])

            writer.writerow([])

            # Resumen Bloom
            writer.writerow(["# Resumen por Nivel de Bloom"])
            writer.writerow(["Nivel", "Preguntas", "p-valor promedio"])
            for bloom, stats in sorted(bloom_stats.items()):
                avg_pv = stats["p_value_sum"] / stats["count"]
                writer.writerow([bloom, stats["count"], f"{avg_pv:.3f}"])

            writer.writerow([])

            # Alertas
            writer.writerow(["# Preguntas que requieren revisión del banco"])
            writer.writerow(["Tipo", "N°", "Pregunta (extracto)", "p-valor"])
            for item in too_easy:
                pv = float(item.get("p_value") or 0)
                writer.writerow(["Muy fácil (p>0.9)", "—", item["question_text"][:60], f"{pv:.3f}"])
            for item in too_hard:
                pv = float(item.get("p_value") or 0)
                writer.writerow(["Muy difícil (p<0.2)", "—", item["question_text"][:60], f"{pv:.3f}"])

    logger.info(
        f"Reporte [{fmt}] generado: {output_path} "
        f"({len(items)} preguntas, {len(scores)} estudiantes)"
    )
    logger.info(
        f"Alertas: {len(too_easy)} muy fácil(es), {len(too_hard)} muy difícil(es)"
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python generate_analytics.py <exam_id> [output.csv]")
        sys.exit(1)

    _exam_id = sys.argv[1]
    _output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("workspace/generated_exams/analytics.csv")
    generate_full_report(_exam_id, _output)
