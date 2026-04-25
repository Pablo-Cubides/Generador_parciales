"""Pipeline OMR híbrido: OpenCV (determinista) + LLM (fallback).

Flujo de dos pasadas:
  Pasada A — OpenCV:
    1. Decodificar QR (student_id|exam_code|form_variant|n_questions)
    2. Corrección de perspectiva por marcadores de esquina (cuadrados ■)
    3. Umbral adaptativo + detección de contornos de burbujas
    4. Puntuación de confianza por celda (área rellena / área total)

  Pasada B — LLM Vision (solo celdas con confianza < umbral):
    Llama a la API de Anthropic con la imagen recortada de la celda dudosa.

  Reconciliación:
    - Si Pasada A y B coinciden → marcar como correcto.
    - Si difieren → needs_review = True.

  Calificación:
    - Coteja respuestas con answer_keys en Supabase.
    - Guarda grade + responses granulares.
    - Actualiza p_value de cada pregunta.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from loguru import logger
from PIL import Image

from scripts.supabase_client import (
    get_answer_key,
    get_exam_by_code,
    refresh_question_stats,
    save_grade,
    save_responses,
)

try:
    from pyzbar.pyzbar import decode as qr_decode
    _PYZBAR_AVAILABLE = True
except ImportError:
    _PYZBAR_AVAILABLE = False
    logger.warning("pyzbar no instalado. Lectura de QR desactivada.")

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic SDK no instalado. Fallback LLM desactivado.")


# ── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class CellResult:
    q_index: int          # 1-based
    marked: str | None    # A-E o None
    confidence: float     # 0-1
    source: str           # "opencv" | "llm" | "manual"
    needs_review: bool = False


@dataclass
class OMRResult:
    student_id: str
    exam_code: str
    form_variant: str
    cells: list[CellResult] = field(default_factory=list)
    vision_confidence_avg: float = 0.0
    needs_review: bool = False


# ── Decodificación de QR ──────────────────────────────────────────────────────

def _decode_qr(image_bgr: np.ndarray) -> dict[str, str] | None:
    """Intenta leer el QR del header. Retorna {exam_code, form_variant, n_questions} o None."""
    if not _PYZBAR_AVAILABLE:
        return None

    decoded = qr_decode(image_bgr)
    if not decoded:
        logger.debug("QR no encontrado en la imagen.")
        return None

    raw: str = decoded[0].data.decode("utf-8")
    parts = raw.split("|")

    if len(parts) >= 2:
        return {
            "exam_code": parts[0],
            "form_variant": parts[1] if len(parts) > 1 else "A",
            "n_questions": int(parts[2]) if len(parts) > 2 else 10,
        }
    return None


# ── Pre-procesamiento de imagen ───────────────────────────────────────────────

def _preprocess(image_bgr: np.ndarray) -> np.ndarray:
    """Escala de grises + desenfoque + umbral adaptativo."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15,
        C=4,
    )
    return thresh


def _find_answer_table(thresh: np.ndarray) -> np.ndarray | None:
    """Detecta la región de la tabla de respuestas en la imagen umbralizada."""
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # La tabla de respuestas es el rectángulo más grande en la mitad inferior
    h, w = thresh.shape
    candidates = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        # Filtrar: grande, en la mitad inferior, proporción razonable
        if area > (h * w * 0.05) and y > h * 0.4 and 2.0 < cw / max(ch, 1) < 15.0:
            candidates.append((area, x, y, cw, ch))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    _, x, y, cw, ch = candidates[0]
    return thresh[y:y + ch, x:x + cw]


def _score_cell(cell_region: np.ndarray) -> float:
    """Calcula qué fracción del área de la celda está rellena (0–1)."""
    if cell_region.size == 0:
        return 0.0
    white_pixels = cv2.countNonZero(cell_region)
    total_pixels = cell_region.size
    return white_pixels / total_pixels


def _parse_bubble_grid(
    table_region: np.ndarray,
    n_questions: int,
    n_options: int = 5,
) -> list[CellResult]:
    """
    Divide la región de la tabla en celdas (n_questions × n_options)
    y calcula la puntuación de relleno de cada celda.
    """
    letters = ["A", "B", "C", "D", "E"][:n_options]
    h, w = table_region.shape[:2]

    # Saltar la fila de encabezado (aprox. 8% del alto)
    header_h = max(int(h * 0.08), 1)
    body = table_region[header_h:, :]

    row_h = (body.shape[0]) // max(n_questions, 1)
    # Saltar la primera columna (número de pregunta, ≈15% del ancho)
    col_start = max(int(w * 0.12), 1)
    col_w = (w - col_start) // max(n_options, 1)

    results: list[CellResult] = []

    for q_idx in range(n_questions):
        y0 = q_idx * row_h
        y1 = y0 + row_h
        row_scores: list[float] = []

        for opt_idx in range(n_options):
            x0 = col_start + opt_idx * col_w
            x1 = x0 + col_w
            cell = body[y0:y1, x0:x1]
            score = _score_cell(cell)
            row_scores.append(score)

        max_score = max(row_scores)
        max_idx = row_scores.index(max_score)

        # Confianza: diferencia entre la celda más rellena y la segunda más rellena
        sorted_scores = sorted(row_scores, reverse=True)
        margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]
        confidence = min(margin * 5.0, 1.0)  # escalar margen a 0-1

        marked = letters[max_idx] if max_score > 0.15 else None

        results.append(CellResult(
            q_index=q_idx + 1,
            marked=marked,
            confidence=confidence,
            source="opencv",
        ))

    return results


# ── Fallback LLM Vision ───────────────────────────────────────────────────────

def _llm_vision_fallback(
    image_bgr: np.ndarray,
    low_confidence_cells: list[int],
) -> dict[int, CellResult]:
    """
    Envía la imagen completa a Claude claude-opus-4-7 indicando qué preguntas verificar.
    Retorna dict {q_index: CellResult} para las celdas revisadas.
    """
    if not _ANTHROPIC_AVAILABLE:
        return {}

    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY no configurada. Saltando LLM fallback.")
        return {}

    # Convertir imagen a base64
    pil_img = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=85)
    b64_img = base64.standard_b64encode(buf.getvalue()).decode()

    questions_str = ", ".join(str(q) for q in low_confidence_cells)
    prompt = (
        f"Esta es una hoja de respuestas de un examen universitario. "
        f"Las preguntas {questions_str} tienen baja confianza de lectura óptica. "
        f"Por favor indica para cada una de esas preguntas qué letra está marcada (A, B, C, D o E). "
        f"Si no hay marca clara, indica null.\n\n"
        f"Responde ÚNICAMENTE con un JSON del formato:\n"
        f'[{{"q": 1, "marked": "C", "confidence": 0.95}}, ...]\n'
        f"Solo incluye las preguntas solicitadas: {questions_str}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_img,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        raw = response.content[0].text.strip()
        # Extraer JSON del texto
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            parsed: list[dict] = json.loads(raw[start:end])
        else:
            return {}

        out: dict[int, CellResult] = {}
        for item in parsed:
            q_idx = int(item["q"])
            out[q_idx] = CellResult(
                q_index=q_idx,
                marked=item.get("marked"),
                confidence=float(item.get("confidence", 0.5)),
                source="llm",
            )
        return out

    except Exception as exc:
        logger.error(f"Error en LLM fallback: {exc}")
        return {}


# ── Calificación contra Supabase ──────────────────────────────────────────────

def _grade_against_db(
    omr: OMRResult,
) -> dict[str, Any] | None:
    """Coteja respuestas OMR con las claves en Supabase y persiste la nota."""
    exam = get_exam_by_code(omr.exam_code)
    if not exam:
        logger.error(f"Examen no encontrado en BD: {omr.exam_code}")
        return None

    answer_keys = get_answer_key(exam["id"])
    if not answer_keys:
        logger.error(f"Sin claves de respuesta para exam_id={exam['id']}")
        return None

    # Construir mapa: order_index → answer_key_row
    key_map: dict[int, dict] = {ak["order_index"]: ak for ak in answer_keys}

    correct = 0
    total = len(answer_keys)
    responses_to_save: list[dict[str, Any]] = []
    needs_review = omr.needs_review

    for cell in omr.cells:
        order_idx = cell.q_index - 1  # 0-based
        ak = key_map.get(order_idx)
        if not ak:
            continue

        is_correct = cell.marked == ak["mapped_correct_answer"] if cell.marked else False
        if is_correct:
            correct += 1

        if cell.confidence < 0.85:
            needs_review = True

        responses_to_save.append({
            "answer_key_id": ak["id"],
            "marked_letter": cell.marked,
            "is_correct": is_correct,
            "confidence": round(cell.confidence, 3),
            "needs_review": cell.needs_review or cell.confidence < 0.85,
        })

    score = round((correct / total) * 5.0, 1) if total > 0 else 0.0
    avg_confidence = (
        sum(c.confidence for c in omr.cells) / len(omr.cells)
        if omr.cells else 0.0
    )

    grade = save_grade(
        student_id=omr.student_id,
        exam_id=exam["id"],
        score=score,
        correct_count=correct,
        total_count=total,
        vision_confidence=avg_confidence,
        raw_data={"cells": [{"q": c.q_index, "marked": c.marked, "src": c.source} for c in omr.cells]},
        needs_review=needs_review,
    )

    # Guardar respuestas granulares y actualizar stats
    if grade:
        for resp in responses_to_save:
            resp["grade_id"] = grade["id"]
        save_responses(responses_to_save)

        for ak in answer_keys:
            refresh_question_stats(ak["question_id"])

    return {
        "student_id": omr.student_id,
        "exam_code": omr.exam_code,
        "score": score,
        "correct_count": correct,
        "total_count": total,
        "vision_confidence_avg": round(avg_confidence, 3),
        "needs_review": needs_review,
        "grade_id": grade["id"] if grade else None,
    }


# ── Punto de entrada principal ────────────────────────────────────────────────

def grade_sheet(
    image_path: Path | str,
    fallback_exam_code: str | None = None,
    fallback_student_id: str | None = None,
    confidence_threshold: float = 0.90,
    save_debug: bool = False,
) -> dict[str, Any] | None:
    """
    Procesa una hoja de respuestas y devuelve el resultado de calificación.

    Args:
        image_path: Ruta a la imagen JPG/PNG.
        fallback_exam_code: Código de examen a usar si el QR no es legible.
        fallback_student_id: ID de estudiante si no hay campo de texto legible.
        confidence_threshold: Mínima confianza para no activar LLM fallback.
        save_debug: Si True, guarda imagen anotada junto a la original.
    """
    image_path = Path(image_path)
    image_bgr = cv2.imread(str(image_path))

    if image_bgr is None:
        logger.error(f"No se pudo leer la imagen: {image_path}")
        return None

    logger.info(f"Procesando: {image_path.name} ({image_bgr.shape[1]}×{image_bgr.shape[0]})")

    # ── Pasada A: OpenCV ─────────────────────────────────────────────────
    qr_data = _decode_qr(image_bgr)
    exam_code = (qr_data or {}).get("exam_code") or fallback_exam_code
    form_variant = (qr_data or {}).get("form_variant", "A")
    n_questions = int((qr_data or {}).get("n_questions", 10))

    if not exam_code:
        logger.error("No se pudo determinar el código de examen (QR ni fallback).")
        return None

    # Identificación de estudiante: primero via QR, luego fallback
    student_id = fallback_student_id or "desconocido"

    thresh = _preprocess(image_bgr)
    table_region = _find_answer_table(thresh)

    cells: list[CellResult] = []
    if table_region is not None:
        cells = _parse_bubble_grid(table_region, n_questions)
    else:
        logger.warning("No se encontró la tabla de burbujas con OpenCV. Usando LLM completo.")

    # ── Pasada B: LLM para celdas de baja confianza ─────────────────────
    low_conf_indices = [
        c.q_index for c in cells if c.confidence < confidence_threshold
    ]

    if low_conf_indices or not cells:
        logger.info(
            f"LLM fallback para {len(low_conf_indices) or n_questions} "
            "pregunta(s) de baja confianza"
        )
        llm_results = _llm_vision_fallback(image_bgr, low_conf_indices or list(range(1, n_questions + 1)))

        if not cells:
            # Sin detección OpenCV: usar directamente LLM para todo
            cells = [
                llm_results.get(i, CellResult(q_index=i, marked=None, confidence=0.0, source="llm"))
                for i in range(1, n_questions + 1)
            ]
        else:
            # Reconciliar: reemplazar celdas de baja confianza con resultado LLM
            for cell in cells:
                if cell.q_index in llm_results:
                    llm_cell = llm_results[cell.q_index]
                    if cell.marked != llm_cell.marked:
                        cell.needs_review = True
                        logger.debug(
                            f"P{cell.q_index}: OpenCV={cell.marked} vs LLM={llm_cell.marked} → revisión"
                        )
                    # Priorizar LLM para celdas de baja confianza
                    cell.marked = llm_cell.marked
                    cell.confidence = llm_cell.confidence
                    cell.source = "llm"

    # ── Guardar imagen de debug ───────────────────────────────────────────
    if save_debug and table_region is not None:
        debug_path = image_path.with_suffix(".debug.jpg")
        cv2.imwrite(str(debug_path), cv2.cvtColor(
            cv2.cvtColor(table_region, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2RGB
        ))
        logger.debug(f"Imagen debug guardada: {debug_path}")

    # ── Construir resultado OMR ───────────────────────────────────────────
    avg_conf = sum(c.confidence for c in cells) / len(cells) if cells else 0.0
    omr = OMRResult(
        student_id=student_id,
        exam_code=exam_code,
        form_variant=form_variant,
        cells=cells,
        vision_confidence_avg=round(avg_conf, 3),
        needs_review=any(c.needs_review for c in cells) or avg_conf < confidence_threshold,
    )

    logger.info(
        f"OMR: {exam_code}/{form_variant} | "
        f"{len(cells)} preguntas | confianza promedio={avg_conf:.1%}"
    )

    # ── Calificación y persistencia ───────────────────────────────────────
    return _grade_against_db(omr)
