import os
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional

from .utils import load_settings, load_env

load_env()


def get_meeting_linker():
    settings = load_settings()
    provider = settings.get("meeting_link", {}).get("provider", "default")
    if provider == "google_calendar":
        return GoogleCalendarLinker(settings["meeting_link"])
    return DefaultLinker(settings.get("meeting_link", {}))


class MeetingLinker:
    def create_meeting(self, title: str, date_time: str, duration_minutes: int = 30) -> dict:
        raise NotImplementedError

    @property
    def name(self) -> str:
        return self.__class__.__name__


class DefaultLinker(MeetingLinker):
    def __init__(self, config: dict):
        self.base_url = config.get("default_link", "https://meet.google.com/new")

    def create_meeting(self, title: str, date_time: str, duration_minutes: int = 30) -> dict:
        meeting_id = str(uuid.uuid4())[:8]
        link = f"https://meet.jit.si/SalesCall-{meeting_id}"
        return {
            "link": link,
            "meeting_id": meeting_id,
            "provider": "jitsi",
            "title": title,
            "date_time": date_time,
        }

    @property
    def name(self) -> str:
        return "default(jitsi)"


class GoogleCalendarLinker(MeetingLinker):
    def __init__(self, config: dict):
        self.creds_path = config.get("credentials_file", "credentials.json")
        self.token_path = config.get("token_file", "token.json")
        self.calendar_id = config.get("calendar_id", "primary")
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError("Install google-api-python-client and google-auth-oauthlib")

        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds = None

        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def create_meeting(self, title: str, date_time: str, duration_minutes: int = 30) -> dict:
        service = self._get_service()

        try:
            dt = datetime.fromisoformat(date_time)
        except ValueError:
            dt = datetime.now() + timedelta(hours=1)

        end_dt = dt + timedelta(minutes=duration_minutes)

        event = {
            "summary": title,
            "start": {
                "dateTime": dt.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "UTC",
            },
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        event = service.events().insert(
            calendarId=self.calendar_id,
            body=event,
            conferenceDataVersion=1,
        ).execute()

        meet_link = event.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri", "")
        return {
            "link": meet_link,
            "event_id": event.get("id", ""),
            "provider": "google_meet",
            "title": title,
            "date_time": date_time,
        }

    @property
    def name(self) -> str:
        return "google_calendar"
