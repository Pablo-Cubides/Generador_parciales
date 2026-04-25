-- Generador de Parciales - Supabase Schema

-- Table for generated question batches
CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    subject TEXT NOT NULL,
    topic TEXT,
    rag_metadata JSONB -- Store which books/sources were used
);

-- Table for the master question bank
CREATE TABLE IF NOT EXISTS public.question_bank (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES public.sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    option_e TEXT NOT NULL,
    correct_answer CHAR(1) NOT NULL, -- The original correct letter (A-E)
    difficulty TEXT,
    has_calculation BOOLEAN DEFAULT false,
    topic TEXT,
    ai_metadata JSONB -- Store Judge feedback, tokens, etc.
);

-- Table for generated exams (Instances)
CREATE TABLE IF NOT EXISTS public.exams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    exam_code TEXT UNIQUE NOT NULL, -- e.g., CALC1-2024-001
    subject TEXT NOT NULL,
    template_name TEXT,
    total_questions INTEGER
);

-- Table for answer keys (Mapped answers per exam instance)
-- This handles the "Option Permutation" logic
CREATE TABLE IF NOT EXISTS public.answer_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id UUID REFERENCES public.exams(id) ON DELETE CASCADE,
    question_id UUID REFERENCES public.question_bank(id),
    order_index INTEGER NOT NULL, -- Position in the exam
    shuffled_options JSONB NOT NULL, -- Map of {original: current} e.g. {"A": "C", "B": "A", ...}
    mapped_correct_answer CHAR(1) NOT NULL -- The letter the student must mark
);

-- Table for grades
CREATE TABLE IF NOT EXISTS public.grades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    student_id TEXT NOT NULL,
    exam_id UUID REFERENCES public.exams(id),
    score NUMERIC(3,1), -- e.g., 4.5
    correct_count INTEGER,
    total_count INTEGER,
    vision_confidence NUMERIC(4,3), -- 0.0 to 1.0
    raw_vision_data JSONB
);
