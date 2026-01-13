from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def create_test_event(creds_dict: dict) -> dict:
    """
    Create a simple test event on the user's primary calendar.
    creds_dict is the stored credentials bundle from your session store.
    """
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict.get("refresh_token"),
        token_uri=creds_dict["token_uri"],
        client_id=creds_dict["client_id"],
        client_secret=creds_dict["client_secret"],
        scopes=creds_dict.get("scopes"),
    )

    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)
    event = {
        "summary": "GG Calendar AI Test Event",
        "description": "Created by GG Calendar AI backend.",
        "start": {"dateTime": now.isoformat()},
        "end": {"dateTime": (now + timedelta(minutes=30)).isoformat()},
    }

    created = service.events().insert(calendarId="primary", body=event).execute()
    return created
