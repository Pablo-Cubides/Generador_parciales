import os
import random
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from supabase_client import get_answer_key, create_exam, save_answer_keys

def generate_docx_exam(exam_id: str, exam_code: str, subject: str, output_path: str):
    # Fetch answer key and questions from Supabase
    data = get_answer_key(exam_id)
    if not data:
        print("No questions found for this exam.")
        return

    doc = Document()

    # Header
    header = doc.sections[0].header
    p = header.paragraphs[0]
    p.text = f"Examen de {subject}\nCódigo: {exam_code}"
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_heading(f"Parcial: {subject}", 0)
    doc.add_paragraph(f"Nombre del Estudiante: _________________________________")
    doc.add_paragraph(f"Código: __________________   Fecha: _________________")
    doc.add_paragraph("-" * 50)

    # Questions
    for i, item in enumerate(data, 1):
        q = item['question_bank']
        shuffled_map = item['shuffled_options'] # e.g. {"A": "C", ...}
        
        # Display questions and options
        doc.add_paragraph(f"{i}. {q['question_text']}", style='List Number')
        
        # Build inverted map to show options in their new position
        # original_options = {"A": q['option_a'], "B": q['option_b'], ...}
        orig = {
            "A": q['option_a'],
            "B": q['option_b'],
            "C": q['option_c'],
            "D": q['option_d'],
            "E": q['option_e']
        }
        
        # We need to show options from A to E based on shuffled_map
        # If shuffled_map["A"] = "C", then the text of A goes to position C
        display_options = {}
        for original_letter, current_letter in shuffled_map.items():
            display_options[current_letter] = orig[original_letter]
            
        for letter in ["A", "B", "C", "D", "E"]:
            doc.add_paragraph(f"   {letter}) {display_options[letter]}")

    # Add Circle Table at the end
    doc.add_page_break()
    doc.add_heading("Tabla de Respuestas", level=1)
    doc.add_paragraph("Rellene completamente el círculo correspondiente a su respuesta.")
    
    table = doc.add_table(rows=len(data) + 1, cols=6)
    table.style = 'Table Grid'
    
    # Header row
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Pregunta"
    for i, letter in enumerate(["A", "B", "C", "D", "E"], 1):
        hdr_cells[i].text = letter
        
    # Data rows
    for i in range(len(data)):
        row_cells = table.rows[i+1].cells
        row_cells[0].text = str(i+1)
        for j in range(1, 6):
            row_cells[j].text = " ( ) "

    doc.save(output_path)
    print(f"Exam saved to {output_path}")

def prepare_exam_shuffling(session_id: str, exam_code: str, subject: str, question_count: int = 10):
    # 1. Get pool of questions
    from supabase_client import get_questions_by_session
    pool = get_questions_by_session(session_id)
    if not pool:
        print("No questions in pool.")
        return
    
    selected = random.sample(pool, min(question_count, len(pool)))
    
    # 2. Create exam record
    exam = create_exam(exam_code, subject, len(selected))
    exam_id = exam['id']
    
    # 3. Create shuffled answer keys
    keys_to_save = []
    letters = ["A", "B", "C", "D", "E"]
    
    for i, q in enumerate(selected):
        current_letters = letters.copy()
        random.shuffle(current_letters)
        
        # shuffled_map: original_letter -> current_letter
        shuffled_map = {orig: curr for orig, curr in zip(letters, current_letters)}
        
        # mapped_correct: what letter is the original correct answer now?
        mapped_correct = shuffled_map[q['correct_answer']]
        
        keys_to_save.append({
            "exam_id": exam_id,
            "question_id": q['id'],
            "order_index": i,
            "shuffled_options": shuffled_map,
            "mapped_correct_answer": mapped_correct
        })
        
    save_answer_keys(keys_to_save)
    return exam_id

if __name__ == "__main__":
    # This is a test usage
    # exam_id = prepare_exam_shuffling("SESSION_ID", "TEST-001", "Cálculo")
    # generate_docx_exam(exam_id, "TEST-001", "Cálculo", "workspace/generated_exams/test_exam.docx")
    pass
