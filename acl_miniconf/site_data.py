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
        if self.session_name.startswith("D"):
            # demo sessions
            return f"Demo Session {self.session_name[1:]}: {start_date}"
        if self.session_name.startswith("P-"):
            # plenary sessions
            return f"{self.session_name[2:]}: {start_date}"
        if self.session_name.startswith("S-"):
            # social event sessions
            return f"{self.session_name[2:]}: {start_date}"
        if self.session_name.startswith("T-"):
            # workshop sessions
            return f"{self.session_name[2:]}: {start_date}"
        if self.session_name.startswith("W-"):
            # workshop sessions
            return f"{self.session_name[2:]}: {start_date}"
        if self.session_name.startswith("z") or self.session_name.startswith("g"):
            # paper sessions
            prefix = self.session_type.capitalize()
            return f"{prefix}-{self.session_name[1:]}: {start_date}"

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
class PaperContent:
    """The content of a paper.

    Needs to be synced with static/js/papers.js and static/js/paper_vis.js.
    """

    # needs to be synced with
    title: str
    authors: List[str]
    track: str
    paper_type: str
    abstract: str
    tldr: str
    keywords: List[str]
    pdf_url: Optional[str]
    demo_url: Optional[str]
    sessions: List[SessionInfo]
    similar_paper_uids: List[str]
    program: str
    material: str = None

    def __post_init__(self):
        if self.program != "workshop" and self.program != "findings":
            assert self.track, self
        if self.pdf_url:
            assert self.pdf_url.startswith("https://"), self.pdf_url
        if self.demo_url:
            assert self.demo_url.startswith("https://") or self.demo_url.startswith(
                "http://"
            ), self.demo_url


@dataclass(frozen=True)
class Paper:
    """The paper dataclass.

    This corresponds to an entry in the `papers.json`.
    See the `start()` method in static/js/papers.js.
    """

    id: str
    forum: str
    card_image_path: str
    presentation_id: str
    content: PaperContent

    @property
    def rocketchat_channel(self) -> str:
        return f"paper-{self.id.replace('.', '-')}"


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
class CommitteeMember:
    role: str
    name: str
    aff: str
    image: Optional[str]


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
    content: PaperContent
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


@dataclass(frozen=True)
class QaSubSession:
    name: str
    link: str
    papers: List[str]


@dataclass(frozen=True)
class QaSession:
    uid: str
    name: str
    start_time: datetime
    end_time: datetime
    subsessions: List[QaSubSession]

    @property
    def time_string(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        end = self.end_time.astimezone(pytz.utc)
        return "({}-{} UTC)".format(start.strftime("%H:%M"), end.strftime("%H:%M"))

    @property
    def day(self) -> str:
        start_time = self.start_time.astimezone(pytz.utc)
        return start_time.strftime("%b %d")
