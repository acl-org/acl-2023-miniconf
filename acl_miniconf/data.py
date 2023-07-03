from collections import defaultdict
from typing import List, Optional, Dict, Any
import glob
import datetime
from pathlib import Path

from pydantic import BaseModel
from .import_booklet_acl2023 import generate_plenaries, generate_tutorials, generate_workshops
import json
import pytz
import yaml

MAIN = "Main"
WORKSHOP = "Workshop"
FINDINGS = "Findings"
DEMO = "Demo"
INDUSTRY = "Industry"
PROGRAMS = {MAIN, WORKSHOP, FINDINGS, DEMO, INDUSTRY}


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
    chairs: List[str] = None
    paper_ids: List[str] = None
    link: Optional[str] = None
    room: Optional[str] = None

    @property
    def day(self) -> str:
        start_time = self.start_time.astimezone(pytz.utc)
        return start_time.strftime("%b %d")

    @property
    def conference_datetime(self) -> str:
        start = self.start_time
        end = self.end_time
        return "{}, {}-{}".format(
            start.strftime("%b %d"),
            start.strftime("%H:%M"),
            end.strftime("%H:%M (%Z)"),
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


class Session(BaseModel):
    id: str
    name: str
    start_time: Optional[datetime.datetime]
    end_time: Optional[datetime.datetime]
    type: str
    events: Dict[str, Event]

    @property
    def day(self) -> str:
        return self.start_time.astimezone(pytz.utc).strftime("%b %d")

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
    forum: str
    card_image_path: str
    title: str
    authors: List[str]
    track: str
    paper_type: str
    category: str
    abstract: str
    tldr: str
    keywords: List[str] = []
    underline_url: Optional[str] = None
    underline_id: Optional[int] = None
    preview_image: Optional[str] = None
    poster_pdf: Optional[str] = None
    slides_pdf: Optional[str] = None
    video_url: Optional[str] = None
    paper_pdf: Optional[str] = None
    demo_url: Optional[str] = None
    event_ids: List[str]
    similar_paper_ids: List[str] = []
    program: str
    material: str = None

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
    plenary_sessions: Dict[str, Any] = {}
    tutorials: Dict[str, Any] = {}
    workshops: Dict[str, Any] = {}
    sponsors: Dict[str, Any] = {}
    plenaries: Dict[str, Any] = {}


class Conference(BaseModel):
    # Time slots, e.g. Session 1
    sessions: Dict[str, Session]
    # All the papers
    papers: Dict[str, Paper]
    # Sessions have events (e.g., Oral session for NLP Applications, or a poster session)
    events: Dict[str, Event]

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


PLENARIES = "Plenary Sessions"
TUTORIALS = "Tutorials"
WORKSHOPS = "Workshops"
PAPER_SESSIONS = "Paper Sessions"
SOCIALS = "Socials"
SPONSORS = "Sponsors"
EVENT_TYPES = {
    PLENARIES,
    TUTORIALS,
    WORKSHOPS,
    PAPER_SESSIONS,
    SOCIALS,
    SPONSORS,
}


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
    plenary_sessions: Dict
    plenary_session_days: Any
    papers: List[Paper] = []
    main_papers: List[Paper] = []
    demo_papers: List[Paper] = []
    findings_papers: List[Paper] = []
    workshop_papers: List[Paper] = []
    tutorials: Any
    tutorials_calendar: Any
    workshops: List[Any] = []
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
    def from_conference(cls, conference: Conference, site_data_path: Path,
                        booklet_info: Path = None):
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
        try:
            with open(booklet_info, 'r') as fp:
                booklet_data = json.load(fp)
            plenary_sessions = generate_plenaries(booklet_data['plenaries'])
            days = list(plenary_sessions.keys())
            days.sort()  # Hack fix
            plenary_session_days = [(idx, day, True) for idx, day in enumerate(days)]
            tutorials = generate_tutorials(booklet_data['tutorials'])
            workshops = generate_workshops(booklet_data['workshops'])
        except FileNotFoundError:
            plenary_sessions = {}
            plenary_session_days = []
            tutorials = {}
            workshops = []
        else:
            pass
        site_data = cls(
            config=config,
            pages=load_all_pages_texts(site_data_path),
            committee={},
            calendar=[],
            papers=list(conference.papers.values()),
            overall_calendar=[],
            session_types=[],
            plenary_sessions=plenary_sessions,
            plenary_session_days=plenary_session_days,
            main_papers=conference.main_papers,
            demo_papers=conference.demo_papers,
            findings_papers=conference.findings_papers,
            workshop_papers=conference.workshop_papers,
            tutorials=tutorials,
            tutorials_calendar=[],
            workshops=workshops,
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
