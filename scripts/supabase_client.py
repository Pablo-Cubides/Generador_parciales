"""Supabase client centralizado para el Generador de Parciales."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from supabase import Client, create_client

load_dotenv()

_url: str = os.environ.get("SUPABASE_URL", "")
_key: str = os.environ.get("SUPABASE_KEY", "")

if not _url or not _key:
    raise ValueError("Faltan SUPABASE_URL o SUPABASE_KEY en las variables de entorno.")

supabase: Client = create_client(_url, _key)


# ── Cursos ────────────────────────────────────────────────────────────────────

def create_course(instructor_id: str, name: str, code: str, term: str) -> dict[str, Any]:
    data = {"instructor_id": instructor_id, "name": name, "code": code, "term": term}
    result = supabase.table("courses").insert(data).execute()
    logger.info(f"Curso creado: {code} — {name}")
    return result.data[0]


def get_courses(instructor_id: str) -> list[dict[str, Any]]:
    result = supabase.table("courses").select("*").eq("instructor_id", instructor_id).execute()
    return result.data


# ── Sesiones ──────────────────────────────────────────────────────────────────

def save_session(
    instructor_id: str,
    subject: str,
    topic: str | None = None,
    course_id: str | None = None,
    rag_metadata: dict | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "instructor_id": instructor_id,
        "subject": subject,
        "topic": topic,
        "course_id": course_id,
        "rag_metadata": rag_metadata,
    }
    result = supabase.table("sessions").insert(data).execute()
    session = result.data[0]
    logger.info(f"Sesión creada: {session['id']} — {subject}/{topic}")
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    result = supabase.table("sessions").select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None


# ── Banco de preguntas ────────────────────────────────────────────────────────

def save_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta un lote de preguntas en question_bank."""
    result = supabase.table("question_bank").insert(questions).execute()
    logger.info(f"{len(result.data)} preguntas guardadas.")
    return result.data


def update_question_status(
    question_id: str,
    status: str,
    judge_scores: dict | None = None,
) -> dict[str, Any]:
    """Actualiza el estado de una pregunta tras la revisión del Judge."""
    data: dict[str, Any] = {"status": status}
    if judge_scores:
        data["judge_scores"] = judge_scores
    result = (
        supabase.table("question_bank").update(data).eq("id", question_id).execute()
    )
    return result.data[0]


def get_questions_by_session(
    session_id: str,
    status: str = "aprobada",
    bloom_levels: list[str] | None = None,
    difficulty: str | None = None,
) -> list[dict[str, Any]]:
    query = (
        supabase.table("question_bank")
        .select("*")
        .eq("session_id", session_id)
        .eq("status", status)
    )
    if bloom_levels:
        query = query.in_("bloom_level", bloom_levels)
    if difficulty:
        query = query.eq("difficulty", difficulty)
    result = query.execute()
    return result.data


def find_similar_questions(
    embedding: list[float],
    threshold: float = 0.92,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Detecta preguntas semánticamente duplicadas mediante pgvector."""
    result = supabase.rpc(
        "find_similar_questions",
        {
            "query_embedding": embedding,
            "similarity_threshold": threshold,
            "max_results": max_results,
        },
    ).execute()
    return result.data


# ── Fuentes RAG ───────────────────────────────────────────────────────────────

def save_rag_source(
    session_id: str,
    title: str,
    chunk_text: str,
    page_number: int | None = None,
    embedding: list[float] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "session_id": session_id,
        "title": title,
        "chunk_text": chunk_text,
        "page_number": page_number,
        "embedding": embedding,
    }
    result = supabase.table("rag_sources").insert(data).execute()
    return result.data[0]


# ── Exámenes ──────────────────────────────────────────────────────────────────

def create_exam(
    instructor_id: str,
    exam_code: str,
    subject: str,
    total_questions: int,
    course_id: str | None = None,
    form_variant: str = "A",
    parent_exam_id: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "instructor_id": instructor_id,
        "exam_code": exam_code,
        "subject": subject,
        "total_questions": total_questions,
        "course_id": course_id,
        "form_variant": form_variant,
        "parent_exam_id": parent_exam_id,
    }
    result = supabase.table("exams").insert(data).execute()
    exam = result.data[0]
    logger.info(f"Examen creado: {exam_code} (Forma {form_variant}), id={exam['id']}")
    return exam


def get_exam_by_code(exam_code: str) -> dict[str, Any] | None:
    result = supabase.table("exams").select("*").eq("exam_code", exam_code).execute()
    return result.data[0] if result.data else None


# ── Claves de respuesta ───────────────────────────────────────────────────────

def save_answer_keys(keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = supabase.table("answer_keys").insert(keys).execute()
    logger.debug(f"{len(result.data)} claves de respuesta guardadas.")
    return result.data


def get_answer_key(exam_id: str) -> list[dict[str, Any]]:
    """Retorna claves con la pregunta anidada, ordenadas por order_index."""
    result = (
        supabase.table("answer_keys")
        .select("*, question_bank(*)")
        .eq("exam_id", exam_id)
        .order("order_index")
        .execute()
    )
    return result.data


# ── Calificaciones ────────────────────────────────────────────────────────────

def save_grade(
    student_id: str,
    exam_id: str,
    score: float,
    correct_count: int,
    total_count: int,
    vision_confidence: float,
    raw_data: dict,
    needs_review: bool = False,
) -> dict[str, Any]:
    data = {
        "student_id": student_id,
        "exam_id": exam_id,
        "score": round(score, 1),
        "correct_count": correct_count,
        "total_count": total_count,
        "vision_confidence": round(vision_confidence, 3),
        "needs_review": needs_review,
        "raw_vision_data": raw_data,
    }
    result = supabase.table("grades").insert(data).execute()
    grade = result.data[0]
    logger.info(f"Nota guardada: student={student_id} exam={exam_id} score={score} review={needs_review}")
    return grade


def save_responses(responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Guarda respuestas granulares por pregunta para análisis posterior."""
    result = supabase.table("responses").insert(responses).execute()
    return result.data


def get_grades_by_exam(exam_id: str) -> list[dict[str, Any]]:
    result = supabase.table("grades").select("*").eq("exam_id", exam_id).execute()
    return result.data


# ── Análisis de ítems ─────────────────────────────────────────────────────────

def compute_item_analysis(exam_id: str) -> list[dict[str, Any]]:
    """Llama a la función SQL para calcular p-value por pregunta."""
    result = supabase.rpc("compute_item_analysis", {"p_exam_id": exam_id}).execute()
    return result.data


def refresh_question_stats(question_id: str) -> None:
    """Actualiza times_used, times_correct y p_value de una pregunta."""
    supabase.rpc("refresh_question_stats", {"p_question_id": question_id}).execute()
