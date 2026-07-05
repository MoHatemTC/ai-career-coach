from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from pydantic import BaseModel

from app.main import app


client = TestClient(app)


def test_parse_uploaded_cv_success():
    fake_pdf_content = b"%PDF-1.4 fake pdf content"

    fake_parsed_cv = {
        "name": "Hady Yasser",
        "email": "hady@example.com",
        "skills": ["Python", "FastAPI", "SQL"]
    }

    with patch("app.api.v1.cvs.cv_parser_graph.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = {
            "parsed_cv": fake_parsed_cv
        }

        response = client.post(
            "/api/v1/cv",
            files={
                "file": (
                    "test_cv.pdf",
                    fake_pdf_content,
                    "application/pdf"
                )
            }
        )

    assert response.status_code == 200
    # The route wraps the parsed CV in a CVParseResponse (user_id is None when the
    # parsed result is not a persisted UserProfile).
    assert response.json() == {"user_id": None, "parsed_cv": fake_parsed_cv}
    mock_invoke.assert_awaited_once()

    call_args = mock_invoke.call_args[0][0]

    assert "file" in call_args
    assert "raw_text" in call_args
    assert "parsed_cv" in call_args
    assert call_args["raw_text"] == ""
    assert call_args["parsed_cv"] is None


def test_parse_uploaded_cv_rejects_non_pdf():
    response = client.post(
        "/api/v1/cv",
        files={
            "file": (
                "test.txt",
                b"this is not a pdf",
                "text/plain"
            )
        }
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Only PDF files are allowed"
    }


class FakeCV(BaseModel):
    name: str
    email: str
    skills: list[str]


def test_parse_uploaded_cv_with_pydantic_model():
    fake_pdf_content = b"%PDF-1.4 fake pdf content"

    fake_model = FakeCV(
        name="Hady Yasser",
        email="hady@example.com",
        skills=["Python", "FastAPI"]
    )

    with patch("app.api.v1.cvs.cv_parser_graph.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = {
            "parsed_cv": fake_model
        }

        response = client.post(
            "/api/v1/cv",
            files={
                "file": (
                    "test_cv.pdf",
                    fake_pdf_content,
                    "application/pdf"
                )
            }
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": None,
        "parsed_cv": {
            "name": "Hady Yasser",
            "email": "hady@example.com",
            "skills": ["Python", "FastAPI"],
        },
    }