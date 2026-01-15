from __future__ import annotations

import secrets
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from app.core.config import settings
from app.services.google_oauth import build_flow
from app.services.calendar_service import (
    create_test_event,
    list_upcoming_events,
    list_events_on_day,
    freebusy_query,
    create_event,
)
from app.services.ai_service import propose_free_slots
from app.services.llm_intent import parse_intent_with_llm

app = FastAPI(title="GG Calendar AI")

# ----------------------------
# CORS (Vite -> FastAPI) with cookies
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Session cookie (dev)
# ----------------------------
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.APP_SECRET_KEY,
    same_site="lax",
    https_only=False,  # dev only
    session_cookie="gg_session",
    max_age=60 * 60 * 24,  # 1 day
)

# In-memory creds store (dev only)
CREDENTIALS_BY_SESSION: Dict[str, Dict[str, Any]] = {}
OAUTH_STATE_BY_SESSION: Dict[str, str] = {}

# ----------------------------
# Helpers
# ----------------------------
def _get_or_create_sid(request: Request) -> str:
    sid = request.session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(24)
        request.session["sid"] = sid
    return sid


def _save_credentials_to_session(request: Request, creds) -> None:
    sid = _get_or_create_sid(request)
    CREDENTIALS_BY_SESSION[sid] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
    }


def _require_auth(request: Request) -> Dict[str, Any]:
    sid = request.session.get("sid")
    if not sid or sid not in CREDENTIALS_BY_SESSION:
        raise HTTPException(status_code=401, detail="Not authenticated. Visit /auth/google/login first.")
    return CREDENTIALS_BY_SESSION[sid]


def _build_google_flow():
    return build_flow()

# ----------------------------
# Basic endpoints
# ----------------------------
@app.get("/")
def root():
    return {"message": "Backend running", "health": "/health", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/status")
def auth_status(request: Request):
    sid = request.session.get("sid")
    return {"authenticated": bool(sid and sid in CREDENTIALS_BY_SESSION)}


@app.post("/auth/logout")
def auth_logout_post(request: Request):
    sid = request.session.get("sid")
    if sid:
        CREDENTIALS_BY_SESSION.pop(sid, None)
        OAUTH_STATE_BY_SESSION.pop(sid, None)
    request.session.clear()
    return {"ok": True}


@app.get("/auth/logout")
def auth_logout_get(request: Request):
    # convenience for browser testing
    return auth_logout_post(request)

# ----------------------------
# OAuth
# ----------------------------
@app.get("/auth/google/login")
def google_login(request: Request):
    flow = _build_google_flow()

    # Ensure session + sid exists BEFORE redirecting away
    sid = _get_or_create_sid(request)

    state = secrets.token_urlsafe(32)
    OAUTH_STATE_BY_SESSION[sid] = state

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return RedirectResponse(url=auth_url, status_code=302)



@app.get("/auth/google/callback")
def google_callback(request: Request, state: Optional[str] = None, code: Optional[str] = None):
    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing state or code from Google.")

    sid = request.session.get("sid")
    expected_state = OAUTH_STATE_BY_SESSION.get(sid) if sid else None

    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    # one-time use
    if sid:
        OAUTH_STATE_BY_SESSION.pop(sid, None)

    flow = _build_google_flow()
    flow.fetch_token(code=code)

    _save_credentials_to_session(request, flow.credentials)

    return RedirectResponse(url=f"{settings.FRONTEND_ORIGIN}/?oauth=success", status_code=302)

# ----------------------------
# Calendar endpoints
# ----------------------------
@app.get("/calendar/test-event")
def calendar_test_event(request: Request):
    creds_dict = _require_auth(request)
    created = create_test_event(creds_dict)
    return {
        "message": "Event created",
        "id": created.get("id"),
        "htmlLink": created.get("htmlLink"),
        "summary": created.get("summary"),
        "start": created.get("start"),
        "end": created.get("end"),
    }


@app.get("/calendar/upcoming")
def calendar_upcoming(request: Request, days: int = 7):
    creds_dict = _require_auth(request)
    items = list_upcoming_events(creds_dict, days=days)
    return {"days": days, "count": len(items), "items": items}


@app.get("/calendar/day")
def calendar_day(request: Request, date: str):
    creds_dict = _require_auth(request)
    items = list_events_on_day(creds_dict, date)
    return {"date": date, "count": len(items), "items": items}


class FreeBusyRequest(BaseModel):
    start: str
    end: str


@app.post("/calendar/freebusy")
def calendar_freebusy(payload: FreeBusyRequest, request: Request):
    creds_dict = _require_auth(request)
    fb = freebusy_query(creds_dict, payload.start, payload.end)
    busy = fb.get("calendars", {}).get("primary", {}).get("busy", [])
    return {"start": payload.start, "end": payload.end, "busy": busy, "is_free": len(busy) == 0}


class CreateEventRequest(BaseModel):
    summary: str
    start: str
    end: str
    description: str | None = None
    timezone: str | None = None


@app.post("/calendar/create")
def calendar_create(payload: CreateEventRequest, request: Request):
    creds_dict = _require_auth(request)
    created = create_event(
        creds_dict,
        summary=payload.summary,
        start_iso=payload.start,
        end_iso=payload.end,
        description=payload.description,
        timezone=payload.timezone,
    )
    return {
        "message": "Event created",
        "id": created.get("id"),
        "htmlLink": created.get("htmlLink"),
        "summary": created.get("summary"),
        "start": created.get("start"),
        "end": created.get("end"),
    }

# ----------------------------
# AI propose (rule-based)
# ----------------------------
class AiProposeRequest(BaseModel):
    start: str
    end: str
    duration_minutes: int = 30
    limit: int = 5


@app.post("/ai/propose")
def ai_propose(payload: AiProposeRequest, request: Request):
    creds_dict = _require_auth(request)
    fb = freebusy_query(creds_dict, payload.start, payload.end)

    out = propose_free_slots(
        window_start_iso=payload.start,
        window_end_iso=payload.end,
        duration_minutes=payload.duration_minutes,
        limit=payload.limit,
        freebusy_response=fb,
    )
    return out

# ----------------------------
# AI plan (natural language -> intent -> freebusy -> proposals)
# ----------------------------
class AiPlanRequest(BaseModel):
    prompt: str
    limit: int = 5


@app.post("/ai/plan")
def ai_plan(payload: AiPlanRequest, request: Request):
    creds_dict = _require_auth(request)

    intent = parse_intent_with_llm(payload.prompt)

    fb = freebusy_query(creds_dict, intent.start, intent.end)

    result = propose_free_slots(
        window_start_iso=intent.start,
        window_end_iso=intent.end,
        duration_minutes=intent.duration_minutes,
        limit=payload.limit,
        freebusy_response=fb,
    )

    result["prompt"] = payload.prompt
    result["parsed_intent"] = intent.model_dump()
    return result
