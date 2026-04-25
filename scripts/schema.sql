-- ============================================================
-- Generador de Parciales AI — Schema v2.0
-- Ejecutar en Supabase SQL Editor
-- ============================================================

-- ── Extensiones ─────────────────────────────────────────────
create extension if not exists "pgvector"  with schema public;
create extension if not exists "uuid-ossp" with schema public;

-- ── Tipos enumerados ─────────────────────────────────────────
do $$ begin
  create type public.bloom_level as enum (
    'recordar','entender','aplicar','analizar','evaluar','crear'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.difficulty_level as enum (
    'muy_facil','facil','medio','dificil','muy_dificil'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.question_status as enum (
    'pendiente','aprobada','rechazada','en_revision'
  );
exception when duplicate_object then null; end $$;

-- ── Función auxiliar updated_at ──────────────────────────────
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ── Tabla: courses ───────────────────────────────────────────
create table if not exists public.courses (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz default now() not null,
  updated_at    timestamptz default now() not null,
  instructor_id uuid references auth.users(id) on delete cascade not null,
  name          text not null,
  code          text not null,
  term          text not null,
  is_active     boolean default true
);

create index if not exists courses_instructor_id_idx on public.courses (instructor_id);

drop trigger if exists courses_updated_at on public.courses;
create trigger courses_updated_at
  before update on public.courses
  for each row execute function public.set_updated_at();

-- ── Tabla: sessions ──────────────────────────────────────────
create table if not exists public.sessions (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz default now() not null,
  updated_at    timestamptz default now() not null,
  course_id     uuid references public.courses(id) on delete set null,
  instructor_id uuid references auth.users(id) on delete cascade not null,
  subject       text not null,
  topic         text,
  rag_metadata  jsonb
);

create index if not exists sessions_instructor_id_idx on public.sessions (instructor_id);
create index if not exists sessions_course_id_idx    on public.sessions (course_id);

drop trigger if exists sessions_updated_at on public.sessions;
create trigger sessions_updated_at
  before update on public.sessions
  for each row execute function public.set_updated_at();

-- ── Tabla: rag_sources ───────────────────────────────────────
-- Almacena chunks del material académico con sus embeddings
create table if not exists public.rag_sources (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz default now() not null,
  session_id   uuid references public.sessions(id) on delete cascade not null,
  title        text not null,
  chunk_text   text not null,
  page_number  integer,
  embedding    vector(1536)
);

create index if not exists rag_sources_session_id_idx on public.rag_sources (session_id);
create index if not exists rag_sources_embedding_idx
  on public.rag_sources using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- ── Tabla: question_bank ─────────────────────────────────────
create table if not exists public.question_bank (
  id                uuid primary key default gen_random_uuid(),
  session_id        uuid references public.sessions(id) on delete cascade not null,
  created_at        timestamptz default now() not null,
  updated_at        timestamptz default now() not null,
  question_text     text not null,
  option_a          text not null,
  option_b          text not null,
  option_c          text not null,
  option_d          text not null,
  option_e          text not null,
  correct_answer    char(1) not null
                    check (correct_answer in ('A','B','C','D','E')),
  difficulty        public.difficulty_level default 'medio',
  bloom_level       public.bloom_level default 'entender',
  has_calculation   boolean default false,
  topic             text,
  source_citation   jsonb,  -- {rag_source_id, page, quote}
  status            public.question_status default 'pendiente',
  judge_scores      jsonb,  -- {tiene_citacion, distractor_logico, libre_de_absolutos, unico_correcto, alineado_temario}
  ai_metadata       jsonb,
  embedding         vector(1536),
  -- Item analysis (se actualiza tras cada examen)
  irt_difficulty    numeric(4,3),  -- parámetro b de IRT
  irt_discrimination numeric(4,3), -- parámetro a de IRT
  times_used        integer default 0,
  times_correct     integer default 0,
  p_value           numeric(4,3)   -- times_correct / times_used
);

create index if not exists qb_session_id_idx  on public.question_bank (session_id);
create index if not exists qb_status_idx      on public.question_bank (status);
create index if not exists qb_bloom_idx       on public.question_bank (bloom_level);
create index if not exists qb_difficulty_idx  on public.question_bank (difficulty);
create index if not exists qb_embedding_idx
  on public.question_bank using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

drop trigger if exists question_bank_updated_at on public.question_bank;
create trigger question_bank_updated_at
  before update on public.question_bank
  for each row execute function public.set_updated_at();

-- ── Tabla: exams ─────────────────────────────────────────────
create table if not exists public.exams (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz default now() not null,
  updated_at      timestamptz default now() not null,
  course_id       uuid references public.courses(id) on delete set null,
  instructor_id   uuid references auth.users(id) on delete cascade not null,
  exam_code       text unique not null,
  subject         text not null,
  template_name   text,
  total_questions integer not null,
  form_variant    text default 'A',  -- A, B, C, D…
  parent_exam_id  uuid references public.exams(id) on delete set null  -- para batch variants
);

create index if not exists exams_instructor_id_idx on public.exams (instructor_id);
create index if not exists exams_course_id_idx     on public.exams (course_id);
create index if not exists exams_parent_exam_idx   on public.exams (parent_exam_id);

drop trigger if exists exams_updated_at on public.exams;
create trigger exams_updated_at
  before update on public.exams
  for each row execute function public.set_updated_at();

-- ── Tabla: answer_keys ───────────────────────────────────────
create table if not exists public.answer_keys (
  id                    uuid primary key default gen_random_uuid(),
  exam_id               uuid references public.exams(id) on delete cascade not null,
  question_id           uuid references public.question_bank(id) not null,
  order_index           integer not null,   -- posición 0-based en el examen
  shuffled_options      jsonb not null,     -- {"A":"C","B":"A",...} original→actual
  mapped_correct_answer char(1) not null
                        check (mapped_correct_answer in ('A','B','C','D','E')),
  unique (exam_id, order_index)
);

create index if not exists ak_exam_id_idx     on public.answer_keys (exam_id);
create index if not exists ak_question_id_idx on public.answer_keys (question_id);

-- ── Tabla: grades ────────────────────────────────────────────
create table if not exists public.grades (
  id                uuid primary key default gen_random_uuid(),
  created_at        timestamptz default now() not null,
  student_id        text not null,  -- código del estudiante en texto plano
  exam_id           uuid references public.exams(id) not null,
  score             numeric(3,1) check (score between 0 and 5),
  correct_count     integer,
  total_count       integer,
  vision_confidence numeric(4,3) check (vision_confidence between 0 and 1),
  needs_review      boolean default false,
  raw_vision_data   jsonb
);

create index if not exists grades_exam_id_idx    on public.grades (exam_id);
create index if not exists grades_student_id_idx on public.grades (student_id);

-- ── Tabla: responses ─────────────────────────────────────────
-- Respuesta granular por pregunta (reemplaza el placeholder en analytics)
create table if not exists public.responses (
  id             uuid primary key default gen_random_uuid(),
  grade_id       uuid references public.grades(id) on delete cascade not null,
  answer_key_id  uuid references public.answer_keys(id) not null,
  marked_letter  char(1) check (marked_letter in ('A','B','C','D','E')),
  is_correct     boolean,
  confidence     numeric(4,3) check (confidence between 0 and 1),
  needs_review   boolean default false
);

create index if not exists responses_grade_id_idx      on public.responses (grade_id);
create index if not exists responses_answer_key_id_idx on public.responses (answer_key_id);
create index if not exists responses_is_correct_idx    on public.responses (is_correct);

-- ── Row Level Security ───────────────────────────────────────
alter table public.courses       enable row level security;
alter table public.sessions      enable row level security;
alter table public.rag_sources   enable row level security;
alter table public.question_bank enable row level security;
alter table public.exams         enable row level security;
alter table public.answer_keys   enable row level security;
alter table public.grades        enable row level security;
alter table public.responses     enable row level security;

-- courses: instructor ve y modifica sus propios cursos
drop policy if exists "instructor_owns_course" on public.courses;
create policy "instructor_owns_course" on public.courses
  using  (auth.uid() = instructor_id)
  with check (auth.uid() = instructor_id);

-- sessions: instructor ve y modifica sus propias sesiones
drop policy if exists "instructor_owns_session" on public.sessions;
create policy "instructor_owns_session" on public.sessions
  using  (auth.uid() = instructor_id)
  with check (auth.uid() = instructor_id);

-- rag_sources: acceso vía propiedad de sesión
drop policy if exists "rag_sources_via_session" on public.rag_sources;
create policy "rag_sources_via_session" on public.rag_sources
  using (exists (
    select 1 from public.sessions s
    where s.id = session_id and s.instructor_id = auth.uid()
  ));

-- question_bank: acceso vía propiedad de sesión
drop policy if exists "questions_via_session" on public.question_bank;
create policy "questions_via_session" on public.question_bank
  using (exists (
    select 1 from public.sessions s
    where s.id = session_id and s.instructor_id = auth.uid()
  ));

-- exams: instructor ve y modifica sus propios exámenes
drop policy if exists "instructor_owns_exam" on public.exams;
create policy "instructor_owns_exam" on public.exams
  using  (auth.uid() = instructor_id)
  with check (auth.uid() = instructor_id);

-- answer_keys: NUNCA exponer a anon; solo vía propiedad del examen
drop policy if exists "answer_keys_via_exam" on public.answer_keys;
create policy "answer_keys_via_exam" on public.answer_keys
  using (exists (
    select 1 from public.exams e
    where e.id = exam_id and e.instructor_id = auth.uid()
  ));

-- grades: acceso vía propiedad del examen
drop policy if exists "grades_via_exam" on public.grades;
create policy "grades_via_exam" on public.grades
  using (exists (
    select 1 from public.exams e
    where e.id = exam_id and e.instructor_id = auth.uid()
  ));

-- responses: acceso vía grade vía examen
drop policy if exists "responses_via_grade" on public.responses;
create policy "responses_via_grade" on public.responses
  using (exists (
    select 1 from public.grades g
    join public.exams e on e.id = g.exam_id
    where g.id = grade_id and e.instructor_id = auth.uid()
  ));

-- ── Función: deduplicación semántica ────────────────────────
create or replace function public.find_similar_questions(
  query_embedding vector(1536),
  p_session_id    uuid default null,
  similarity_threshold float default 0.92,
  max_results     int default 5
)
returns table(id uuid, question_text text, similarity float)
language plpgsql security definer
as $$
begin
  return query
  select
    q.id,
    q.question_text,
    round((1 - (q.embedding <=> query_embedding))::numeric, 4)::float as similarity
  from public.question_bank q
  where q.embedding is not null
    and 1 - (q.embedding <=> query_embedding) > similarity_threshold
    and (p_session_id is null or q.session_id = p_session_id)
  order by q.embedding <=> query_embedding
  limit max_results;
end;
$$;

-- ── Función: item analysis por examen ───────────────────────
create or replace function public.compute_item_analysis(p_exam_id uuid)
returns table(
  question_id        uuid,
  question_text      text,
  p_value            numeric,
  total_responses    bigint,
  correct_responses  bigint,
  bloom             public.bloom_level,
  difficulty        public.difficulty_level
)
language plpgsql security definer
as $$
begin
  return query
  select
    ak.question_id,
    qb.question_text,
    round(avg(case when r.is_correct then 1.0 else 0.0 end)::numeric, 3) as p_value,
    count(r.id)                                                           as total_responses,
    count(case when r.is_correct then 1 end)                             as correct_responses,
    qb.bloom_level,
    qb.difficulty
  from public.answer_keys ak
  join public.question_bank qb on qb.id = ak.question_id
  left join public.responses r  on r.answer_key_id = ak.id
  where ak.exam_id = p_exam_id
  group by ak.question_id, qb.question_text, qb.bloom_level, qb.difficulty
  order by p_value asc;
end;
$$;

-- ── Función: actualizar p_value tras calificar ───────────────
create or replace function public.refresh_question_stats(p_question_id uuid)
returns void
language plpgsql security definer
as $$
begin
  update public.question_bank
  set
    times_used    = (
      select count(*) from public.responses r
      join public.answer_keys ak on ak.id = r.answer_key_id
      where ak.question_id = p_question_id
    ),
    times_correct = (
      select count(*) from public.responses r
      join public.answer_keys ak on ak.id = r.answer_key_id
      where ak.question_id = p_question_id and r.is_correct = true
    ),
    p_value = (
      select round(
        case when count(*) = 0 then null
             else avg(case when r.is_correct then 1.0 else 0.0 end)
        end::numeric, 3
      )
      from public.responses r
      join public.answer_keys ak on ak.id = r.answer_key_id
      where ak.question_id = p_question_id
    )
  where id = p_question_id;
end;
$$;
