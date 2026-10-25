"""Keep the CI provider fixture compatible with quiz validation."""

import json

from scripts.mock_openai_server import _response_content
from services.parser.quiz import EXTRACTION_PROMPT
from services.practice.annotation import validate_question_payload


def test_smoke_provider_returns_valid_quiz_questions():
    content = _response_content([
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": "Binary search halves a sorted search interval."},
    ])
    questions = json.loads(content)
    assert len(questions) >= 2
    for question in questions:
        result = validate_question_payload(question, title="Binary Search Basics", source="extracted")
        assert result.is_valid, result.errors
