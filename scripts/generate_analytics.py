import csv
from supabase_client import supabase

def generate_error_report(exam_id: str, output_path: str):
    # 1. Fetch all grades for this exam
    grades_result = supabase.table("grades").select("*").eq("exam_id", exam_id).execute()
    grades = grades_result.data
    
    if not grades:
        print("No grades found for this exam.")
        return

    # 2. Fetch answer key to know question count
    key_result = supabase.table("answer_keys").select("*").eq("exam_id", exam_id).execute()
    question_count = len(key_result.data)

    # 3. Create CSV Matrix
    # Rows: Students, Columns: P1, P2... Pn, Score
    with open(output_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        # Header
        header = ["Estudiante"] + [f"P{i+1}" for i in range(question_count)] + ["Nota"]
        writer.writerow(header)
        
        for g in grades:
            row = [g['student_id']]
            # In a real scenario, we'd compare raw_vision_data with answer_key here
            # For now, we simulate the row
            row += ["✓" for _ in range(question_count)] # Placeholder
            row.append(g['score'])
            writer.writerow(row)
            
    print(f"Analytics report saved to {output_path}")

if __name__ == "__main__":
    # generate_error_report("EXAM_ID", "workspace/generated_exams/analytics.csv")
    pass
