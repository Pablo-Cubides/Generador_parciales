import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in environment variables.")

supabase: Client = create_client(url, key)

def save_session(subject: str, topic: str = None, rag_metadata: dict = None):
    data = {
        "subject": subject,
        "topic": topic,
        "rag_metadata": rag_metadata
    }
    result = supabase.table("sessions").insert(data).execute()
    return result.data[0] if result.data else None

def save_questions(questions: list):
    """
    questions: list of dicts matching question_bank schema
    """
    result = supabase.table("question_bank").insert(questions).execute()
    return result.data

def get_questions_by_session(session_id: str):
    result = supabase.table("question_bank").select("*").eq("session_id", session_id).execute()
    return result.data

def create_exam(exam_code: str, subject: str, total_questions: int):
    data = {
        "exam_code": exam_code,
        "subject": subject,
        "total_questions": total_questions
    }
    result = supabase.table("exams").insert(data).execute()
    return result.data[0] if result.data else None

def save_answer_keys(keys: list):
    result = supabase.table("answer_keys").insert(keys).execute()
    return result.data

def get_answer_key(exam_id: str):
    result = supabase.table("answer_keys").select("*, question_bank(*)").eq("exam_id", exam_id).execute()
    return result.data

def save_grade(student_id: str, exam_id: str, score: float, correct_count: int, total_count: int, vision_confidence: float, raw_data: dict):
    data = {
        "student_id": student_id,
        "exam_id": exam_id,
        "score": score,
        "correct_count": correct_count,
        "total_count": total_count,
        "vision_confidence": vision_confidence,
        "raw_vision_data": raw_data
    }
    result = supabase.table("grades").insert(data).execute()
    return result.data[0] if result.data else None
