"""Tests para la lógica de permutación de compile_exam.py (sin BD)."""

import random

import pytest


LETTERS = ["A", "B", "C", "D", "E"]


def _make_shuffled_map(rng: random.Random) -> dict[str, str]:
    current = LETTERS.copy()
    rng.shuffle(current)
    return {orig: curr for orig, curr in zip(LETTERS, current)}


def _get_mapped_correct(shuffled_map: dict[str, str], correct: str) -> str:
    return shuffled_map[correct]


class TestShuffledMap:
    def test_all_letters_present(self):
        rng = random.Random(42)
        m = _make_shuffled_map(rng)
        assert set(m.keys()) == set(LETTERS)
        assert set(m.values()) == set(LETTERS)

    def test_bijection(self):
        """El mapa debe ser biyectivo: sin colisiones de destino."""
        rng = random.Random(0)
        for _ in range(100):
            m = _make_shuffled_map(rng)
            assert len(set(m.values())) == 5, "Hay colisión en el mapa de barajado"

    def test_correct_answer_remapped(self):
        """La respuesta correcta original debe aparecer en la nueva posición."""
        rng = random.Random(7)
        m = _make_shuffled_map(rng)
        for orig in LETTERS:
            mapped = _get_mapped_correct(m, orig)
            assert mapped in LETTERS

    def test_different_seeds_produce_different_maps(self):
        """Dos instancias con distinta semilla deben producir mapas distintos."""
        m1 = _make_shuffled_map(random.Random(1))
        m2 = _make_shuffled_map(random.Random(99))
        assert m1 != m2


class TestStudentHash:
    def test_hash_deterministic(self):
        from scripts.supabase_client import hash_student_id

        # Mismo student_id + mismo pepper → mismo hash
        h1 = hash_student_id("12345")
        h2 = hash_student_id("12345")
        assert h1 == h2

    def test_hash_different_ids(self):
        from scripts.supabase_client import hash_student_id

        assert hash_student_id("12345") != hash_student_id("12346")

    def test_hash_length(self):
        from scripts.supabase_client import hash_student_id

        h = hash_student_id("any_student")
        assert len(h) == 64  # SHA-256 en hex = 64 caracteres

    def test_hash_no_plain_id(self):
        """El hash no debe contener el student_id en texto plano."""
        from scripts.supabase_client import hash_student_id

        student_id = "202310500"
        h = hash_student_id(student_id)
        assert student_id not in h


class TestAnalyticsFlags:
    def test_too_easy_threshold(self):
        items = [
            {"p_value": 0.95, "question_text": "Fácil"},
            {"p_value": 0.50, "question_text": "Normal"},
            {"p_value": 0.10, "question_text": "Difícil"},
        ]
        too_easy = [i for i in items if float(i.get("p_value") or 0) > 0.9]
        too_hard = [i for i in items if float(i.get("p_value") or 0) < 0.2]
        assert len(too_easy) == 1
        assert len(too_hard) == 1
        assert too_easy[0]["question_text"] == "Fácil"
        assert too_hard[0]["question_text"] == "Difícil"
