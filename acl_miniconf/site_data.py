from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz




@dataclass(frozen=True)
class SessionInfo:
    """The session information for a paper."""

    session_name: str
    start_time: datetime
    end_time: datetime
    link: str
    hosts: str = None

    @property
    def day(self) -> str:
        start_time = self.start_time.astimezone(pytz.utc)
        return f'{start_time.strftime("%b")} {start_time.day}'

    @property
    def time_string(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        end = self.end_time.astimezone(pytz.utc)
        return "({}-{} UTC)".format(start.strftime("%H:%M"), end.strftime("%H:%M"))

    @property
    def start_time_string(self) -> str:
        start_time = self.start_time.astimezone(pytz.utc)
        return start_time.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def end_time_string(self) -> str:
        end_time = self.end_time.astimezone(pytz.utc)
        return end_time.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def session(self) -> str:
        start_time = self.start_time.astimezone(pytz.utc)
        start_date = f'{start_time.strftime("%b")} {start_time.day}'
        return f"Session {self.session_name}: {start_date}"

    @property
    def session_type(self):
        if self.session_name.startswith("z"):
            return "zoom"
        elif self.session_name.startswith("g"):
            return "gather"
        else:
            return "unknown"


@dataclass(frozen=True)
class PlenaryVideo:
    id: str
    title: str
    speakers: str
    presentation_id: Optional[str]


@dataclass(frozen=True)
class PlenarySession:
    id: str
    title: str
    image: str
    day: str
    sessions: List[SessionInfo]
    presenter: Optional[str]
    institution: Optional[str]
    abstract: Optional[str]
    bio: Optional[str]
    # SlidesLive presentation ID
    presentation_id: Optional[str]
    rocketchat_channel: Optional[str]
    videos: List[PlenaryVideo]


@dataclass(frozen=True)
class TutorialSessionInfo:
    """The session information for a tutorial."""

    session_name: str
    start_time: datetime
    end_time: datetime
    hosts: str
    livestream_id: str
    zoom_link: str

    @property
    def time_string(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        end = self.end_time.astimezone(pytz.utc)
        return "({}-{} UTC)".format(start.strftime("%H:%M"), end.strftime("%H:%M"))

    @property
    def start_time_string(self) -> str:
        start_time = self.start_time.astimezone(pytz.utc)
        return start_time.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def end_time_string(self) -> str:
        end_time = self.end_time.astimezone(pytz.utc)
        return end_time.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def session(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        start_date = f'{start.strftime("%b")} {start.day}'
        return f"{self.session_name}: {start_date}"

    @property
    def day(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        start_date = f'{start.strftime("%b")} {start.day}'
        return start_date


@dataclass(frozen=True)
class Tutorial:
    id: str
    title: str
    organizers: List[str]
    abstract: str
    website: Optional[str]
    material: Optional[str]
    slides: Optional[str]
    prerecorded: Optional[str]
    rocketchat_channel: str
    sessions: List[TutorialSessionInfo]
    blocks: List[SessionInfo]
    virtual_format_description: str


@dataclass(frozen=True)
class WorkshopPaper:
    id: str
    title: str
    speakers: str
    presentation_id: Optional[str]
    content: Any
    rocketchat_channel: str


@dataclass(frozen=True)
class Workshop:
    id: str
    title: str
    organizers: List[str]
    abstract: str
    website: str
    livestream: Optional[str]
    papers: List[WorkshopPaper]
    schedule: List[Dict[str, Any]]
    prerecorded_talks: List[Dict[str, Any]]
    rocketchat_channel: str
    sessions: List[SessionInfo]
    blocks: List[SessionInfo]
    zoom_links: List[str]


@dataclass(frozen=True)
class SocialEventOrganizers:
    members: List[str]
    website: str


@dataclass(frozen=True)
class SocialEvent:
    id: str
    name: str
    description: str
    image: str
    location: str
    organizers: SocialEventOrganizers
    sessions: List[SessionInfo]
    rocketchat_channel: str
    website: str
    zoom_link: str
