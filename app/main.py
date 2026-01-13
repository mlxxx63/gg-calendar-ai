from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from app.services.calendar_service import create_test_event

from app.core.config import settings
from app.services.google_oauth import build_flow

app = FastAPI(title="GG Calendar AI")

# Cookie-based session storage (stores OAuth state)
app.add_middleware(SessionMiddleware, secret_key=settings.APP_SECRET_KEY)

# MVP: store credentials in memory (per user session)
# NOTE: This resets when you restart the server. We'll replace with DB later.
CREDENTIALS_BY_SESSION: dict[str, dict] = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/google/login")
def google_login(request: Request):
    flow = build_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    # store state to validate on callback
    request.session["oauth_state"] = state
    return RedirectResponse(url=authorization_url)


@app.get("/auth/google/callback")
def google_callback(request: Request):
    saved_state = request.session.get("oauth_state")
    returned_state = request.query_params.get("state")

    if not saved_state or not returned_state or saved_state != returned_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state. Please try logging in again.")

    flow = build_flow(state=saved_state)
    flow.fetch_token(authorization_response=str(request.url))

    creds = flow.credentials

    # Use session id as a simple key (signed cookie session; good enough for MVP)
    sid = request.session.get("_sid")
    if not sid:
        sid = str(id(request.session))
        request.session["_sid"] = sid

    # Store only what we need (do not return secrets)
    CREDENTIALS_BY_SESSION[sid] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,  # needed for long-lived access
        "token_uri": creds.token_uri,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "scopes": list(creds.scopes) if creds.scopes else [],
    }

    return JSONResponse(
        {
            "message": "OAuth success",
            "has_refresh_token": creds.refresh_token is not None,
            "scopes": list(creds.scopes) if creds.scopes else [],
            "next": "/calendar/test-event",
        }
    )

@app.get("/calendar/test-event")
def calendar_test_event(request: Request):
    sid = request.session.get("_sid")
    if not sid or sid not in CREDENTIALS_BY_SESSION:
        raise HTTPException(status_code=401, detail="Not authenticated. Visit /auth/google/login first.")

    created = create_test_event(CREDENTIALS_BY_SESSION[sid])

    return {
        "message": "Event created",
        "id": created.get("id"),
        "htmlLink": created.get("htmlLink"),
        "summary": created.get("summary"),
        "start": created.get("start"),
        "end": created.get("end"),
    }