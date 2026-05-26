"""FastAPI application entry point.

Run with:  uvicorn backend.main:app --reload   (or use run-backend.bat)
Interactive API docs are served at http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.drafts import router as drafts_router
from backend.api.intake import router as intake_router
from backend.api.routes import router
from backend.config import settings

app = FastAPI(
    title="SmartSupport API",
    description="AI customer-support email automation (study/portfolio project).",
    version="0.1.0",
)

# Allow the React dev server (M2) to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(drafts_router)
app.include_router(intake_router)


@app.get("/health")
def health() -> dict[str, object]:
    """Simple liveness check; also reports whether we're in mock LLM mode."""
    return {"status": "ok", "mock_llm": settings.mock_llm, "model": settings.gemini_model}
