from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def _build_creds(creds_dict: dict) -> Credentials:
    return Credentials(
        token=creds_dict.get("token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri=creds_dict.get("token_uri"),
        client_id=creds_dict.get("client_id"),
        client_secret=creds_dict.get("client_secret"),
        scopes=creds_dict.get("scopes"),
    )


def _build_service(creds_dict: dict):
    creds = _build_creds(creds_dict)
    return build("calendar", "v3", credentials=creds)


def get_calendar_profile(creds_dict: dict) -> dict:
    service = _build_service(creds_dict)
    cal = service.calendars().get(calendarId="primary").execute()
    return {
        "calendarId": "primary",
        "timeZone": cal.get("timeZone", "UTC"),
        "summary": cal.get("summary"),
    }


def _get_primary_tz(creds_dict: dict) -> str:
    # Single source of truth for timezone
    profile = get_calendar_profile(creds_dict)
    return profile.get("timeZone") or "UTC"


def create_test_event(creds_dict: dict) -> dict:
    service = _build_service(creds_dict)

    # Create event using UTC timestamps (Google will display in calendar TZ)
    now = datetime.now(timezone.utc)
    event = {
        "summary": "GG Calendar AI Test Event",
        "description": "Created by GG Calendar AI backend.",
        "start": {"dateTime": now.isoformat()},
        "end": {"dateTime": (now + timedelta(minutes=30)).isoformat()},
    }

    return service.events().insert(calendarId="primary", body=event).execute()


def list_upcoming_events(creds_dict: dict, days: int = 7) -> list[dict]:
    service = _build_service(creds_dict)

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()

    resp = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        )
        .execute()
    )
    return resp.get("items", [])


def list_events_on_day(creds_dict: dict, date_yyyy_mm_dd: str) -> list[dict]:
    """
    IMPORTANT FIX:
    Interpret "day" boundaries in the user's *calendar timezone*,
    then convert to RFC3339 for Google API queries.
    """
    service = _build_service(creds_dict)
    tz_name = _get_primary_tz(creds_dict)
    tz = ZoneInfo(tz_name)

    # Start/end of day in calendar TZ
    start_local = datetime.fromisoformat(f"{date_yyyy_mm_dd}T00:00:00").replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    resp = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start_local.isoformat(),
            timeMax=end_local.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        )
        .execute()
    )
    return resp.get("items", [])


def freebusy_query(creds_dict: dict, start_iso: str, end_iso: str) -> dict:
    service = _build_service(creds_dict)

    body = {
        "timeMin": start_iso,
        "timeMax": end_iso,
        "items": [{"id": "primary"}],
    }

    return service.freebusy().query(body=body).execute()

def create_event(
    creds_dict: dict,
    *,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    timezone: str | None = None,
) -> dict:
    service = _build_service(creds_dict)

    event = {
        "summary": summary,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }

    if description:
        event["description"] = description

    # optional: set explicit timezone (Google can infer from offset, but this is nice to have)
    if timezone:
        event["start"]["timeZone"] = timezone
        event["end"]["timeZone"] = timezone

    return service.events().insert(calendarId="primary", body=event).execute()
