from collections import defaultdict
from typing import List, Optional, Dict, Any
import glob
import datetime
from pathlib import Path

from pydantic import BaseModel
import json
import pytz
import yaml

MAIN = "Main"
WORKSHOP = "Workshop"
FINDINGS = "Findings"
DEMO = "Demo"
INDUSTRY = "Industry"
PROGRAMS = {MAIN, WORKSHOP, FINDINGS, DEMO, INDUSTRY}


PLENARY_TRACK = "Plenary"
WORKSHOP_TRACK = "Workshop"
TUTORIAL_TRACK = "Tutorial"

PLENARIES = "Plenary Sessions"
TUTORIALS = "Tutorials"
WORKSHOPS = "Workshops"
PAPER_SESSIONS = "Paper Sessions"
SOCIALS = "Socials"
SPONSORS = "Sponsors"
BREAKS = "Breaks"
EVENT_TYPES = {
    PLENARIES,
    TUTORIALS,
    WORKSHOPS,
    PAPER_SESSIONS,
    SOCIALS,
    SPONSORS,
    BREAKS,
}
# TODO: Remove this hack/grab from configuration
CONFERENCE_TZ = pytz.timezone("America/Toronto")


def name_to_id(name: str):
    return name.replace(" ", "-").replace(":", "_").lower()


def load_all_pages_texts(site_data_path: str) -> Dict[str, Any]:
    pages_dir = str(Path(site_data_path) / "pages")
    pages = {}
    for page in glob.glob(pages_dir + "/*"):
        with open(page) as f:
            pages_data = f.read()
        page_name = page.split("/")[-1]
        pages[page_name] = pages_data
        print(f"Loaded page data for {page_name}")
    return pages


# These are unique by id, which is determined by session/track/type
# E.G.: id="Session 1: NLP Applications (Oral)"
class Event(BaseModel):
    id: str
    session: str
    track: str
    type: str
    start_time: Optional[datetime.datetime]
    end_time: Optional[datetime.datetime]
    chairs: List[str] = []
    paper_ids: List[str] = []
    link: Optional[str] = None
    room: Optional[str] = None

    @property
    def day(self) -> str:
        start_time = self.start_time.astimezone(pytz.utc)
        return start_time.strftime("%B %d")

    @property
    def conference_datetime(self) -> str:
        start = self.start_time
        end = self.end_time
        return "{}, {}-{}".format(
            start.astimezone(CONFERENCE_TZ).strftime("%B %d"),
            start.astimezone(CONFERENCE_TZ).strftime("%H:%M"),
            end.astimezone(CONFERENCE_TZ).strftime("%H:%M (%Z)"),
        )

    @property
    def time_string(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        end = self.end_time.astimezone(pytz.utc)
        return "({}-{} UTC)".format(start.strftime("%H:%M"), end.strftime("%H:%M"))

    @property
    def start_time_string(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        return start.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def end_time_string(self) -> str:
        end = self.end_time.astimezone(pytz.utc)
        return end.strftime("%Y-%m-%dT%H:%M:%S")


class Plenary(Event):
    title: str
    image_url: Optional[str] = None
    presenter: Optional[str]
    institution: Optional[str]
    abstract: Optional[str]
    bio: Optional[str] = None
    # SlidesLive presentation ID
    video_url: Optional[str] = None
    # Overrides
    type: str = PLENARIES
    track: str = PLENARY_TRACK


class Tutorial(Event):
    title: str
    organizers: List[str]
    description: str
    rocketchat_channel: Optional[str] = None
    type: str = TUTORIALS
    track: str = TUTORIAL_TRACK
    anthology_url: Optional[str] = None
    tutorial_pdf: Optional[str] = None


class AnthologyAuthor(BaseModel):
    first_name: Optional[str]
    middle_name: Optional[str] = None
    last_name: Optional[str]
    full_name: Optional[str] = None
    google_scholar: Optional[str] = None
    semantic_scholar: Optional[str] = None

    @property
    def name(self) -> str:
        if self.full_name is None:
            temp_author = None
            for name in [self.first_name, self.middle_name, self.last_name]:
                if name is not None:
                    if temp_author is None:
                        temp_author = name
                    else:
                        temp_author += f" {name}"
            if temp_author is None:
                raise ValueError("Empty author found")
            else:
                return temp_author
        else:
            return self.full_name


class Workshop(Event):
    short_name: str
    booklet_id: str
    anthology_venue_id: str
    committee: List[AnthologyAuthor]
    workshop_site_url: str
    description: str
    type: str = WORKSHOPS
    track: str = WORKSHOP_TRACK


class Session(BaseModel):
    id: str
    name: str
    display_name: str
    start_time: Optional[datetime.datetime]
    end_time: Optional[datetime.datetime]
    type: str
    events: Dict[str, Event] = {}
    plenary_events: Dict[str, Plenary] = {}
    tutorial_events: Dict[str, Tutorial] = {}
    workshop_events: Dict[str, Workshop] = {}

    @property
    def conference_datetime(self) -> str:
        start = self.start_time
        end = self.end_time
        return "{}, {}-{}".format(
            start.astimezone(CONFERENCE_TZ).strftime("%B %d"),
            start.astimezone(CONFERENCE_TZ).strftime("%H:%M"),
            end.astimezone(CONFERENCE_TZ).strftime("%H:%M (%Z)"),
        )

    @property
    def day(self) -> str:
        # This line was changed because the .js library that builds the calendar
        # expects the dates to have the second format. If we do it the previous
        # way, the `sessions.html` tabs for each day don't work well.
        # return self.start_time.astimezone(pytz.utc).strftime("%B %d")
        return self.start_time.astimezone(pytz.utc).strftime("%B %d")

    @property
    def time_string(self) -> str:
        start = self.start_time.astimezone(pytz.utc)
        end = self.end_time.astimezone(pytz.utc)
        return "({}-{} UTC)".format(start.strftime("%H:%M"), end.strftime("%H:%M"))


class Paper(BaseModel):
    """The content of a paper.

    Needs to be synced with static/js/papers.js and static/js/paper_vis.js.
    """

    id: str
    title: str
    authors: List[str]
    track: str
    paper_type: str
    category: str
    abstract: str
    tldr: str
    keywords: List[str] = []
    languages: List[str] = []
    underline_url: Optional[str] = None
    underline_id: Optional[int] = None
    preview_image: Optional[str] = None
    poster_pdf: Optional[str] = None
    slides_pdf: Optional[str] = None
    video_url: Optional[str] = None
    anthology_url: Optional[str] = None
    paper_pdf: Optional[str] = None
    demo_url: Optional[str] = None
    event_ids: List[str]
    similar_paper_ids: List[str] = []
    program: str
    material: str = None
    is_paper: bool = True
    display_track: Optional[str] = None

    @property
    def rocketchat_channel(self) -> str:
        return f"paper-{self.id.replace('.', '-')}"


class CommitteeMember(BaseModel):
    role: str
    name: str
    affiliation: str
    url: str
    email: str
    image: Optional[str]


class ByUid(BaseModel):
    papers: Dict[str, Paper] = {}
    plenaries: Dict[str, Plenary] = {}
    tutorials: Dict[str, Tutorial] = {}
    workshops: Dict[str, Workshop] = {}


class Conference(BaseModel):
    # Time slots, e.g. Session 1
    sessions: Dict[str, Session]
    # All the papers
    papers: Dict[str, Paper]
    # Sessions have events (e.g., Oral session for NLP Applications, or a poster session)
    events: Dict[str, Event]
    workshops: Dict[str, Workshop] = {}
    plenaries: Dict[str, Plenary] = {}
    tutorials: Dict[str, Tutorial] = {}

    @property
    def main_papers(self):
        return [p for p in self.papers.values() if p.program == MAIN]

    @property
    def workshop_papers(self):
        return [p for p in self.papers.values() if p.program == WORKSHOP]

    @property
    def findings_papers(self):
        return [p for p in self.papers.values() if p.program == FINDINGS]

    @property
    def demo_papers(self):
        return [p for p in self.papers.values() if p.program == DEMO]

    @property
    def industry_papers(self):
        return [p for p in self.papers.values() if p.program == INDUSTRY]


class FrontendCalendarEvent(BaseModel):
    title: str
    start: datetime.datetime
    end: datetime.datetime
    location: str
    url: str
    category: str
    type: str
    view: str
    classNames: List[str] = []


class SiteData(BaseModel):
    config: Any
    pages: Dict[str, str] = {}
    committee: Dict[str, List[CommitteeMember]]
    calendar: List[FrontendCalendarEvent]
    overall_calendar: List[FrontendCalendarEvent]
    session_types: List[str] = []
    # by plenary_id
    plenaries: Dict[str, Plenary]
    papers: List[Paper] = []
    main_papers: List[Paper] = []
    demo_papers: List[Paper] = []
    findings_papers: List[Paper] = []
    workshop_papers: List[Paper] = []
    tutorials: Dict[str, Tutorial] = {}
    tutorials_calendar: Any
    workshops: Dict[str, Workshop] = {}
    socials: Any
    tracks: List[str] = []
    track_ids: List[str] = []
    programs: List[str] = []
    main_program_tracks: List[str] = []
    faq: Any
    local_timezone: str = None
    code_of_conduct: Any
    sessions: Dict[str, Session]
    session_days: List[Any] = []
    sessions_by_day: Dict[str, List[Session]]
    sponsors_by_level: Any
    sponsor_levels: Any

    @classmethod
    def from_conference(
        cls,
        conference: Conference,
        site_data_path: Path,
    ):
        days = set()
        for s in conference.sessions.values():
            days.add(s.day)

        session_days = []
        for i, day in enumerate(sorted(days)):
            session_days.append(
                (day.replace(" ", "").lower(), day, "active" if i == 0 else "")
            )

        sessions_by_day = defaultdict(list)
        for s in conference.sessions.values():
            sessions_by_day[s.day].append(s)

        for day, sessions in sessions_by_day.items():
            sessions_by_day[day] = sorted(sessions, key=lambda x: x.name)

        main_program_tracks = list(
            sorted(
                track
                for track in {
                    paper.track
                    for paper in conference.papers.values()
                    if paper.program == MAIN
                }
            )
        )

        unique_tracks = set()
        unique_track_ids = set()
        for paper in conference.papers.values():
            unique_tracks.add(paper.track)
            unique_track_ids.add(name_to_id(paper.track))
        tracks = sorted(unique_tracks)
        track_ids = list(unique_track_ids)

        with open(site_data_path / "configs" / "config.yml") as f:
            config = yaml.safe_load(f)
        socials = {k: v for k, v in conference.sessions.items() if v.type == "Socials"}
        # Load information about plenary sessions and tutorials from the booklet
        # if the information is available.
        site_data = cls(
            config=config,
            pages=load_all_pages_texts(site_data_path),
            committee={},
            calendar=[],
            papers=list(conference.papers.values()),
            overall_calendar=[],
            session_types=[],
            plenaries=conference.plenaries,
            main_papers=conference.main_papers,
            demo_papers=conference.demo_papers,
            findings_papers=conference.findings_papers,
            workshop_papers=conference.workshop_papers,
            tutorials=conference.tutorials,
            tutorials_calendar=[],
            workshops=conference.workshops,
            socials=socials,
            tracks=tracks,
            track_ids=track_ids,
            main_program_tracks=main_program_tracks,
            faq=[],
            code_of_conduct=[],
            sessions=conference.sessions,
            session_days=session_days,
            sessions_by_day=sessions_by_day,
            sponsors_by_level=[],
            sponsor_levels=[],
            programs=PROGRAMS,
        )
        return site_data
