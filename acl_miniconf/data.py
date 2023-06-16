from typing import List, Optional, Dict
import datetime
from pydantic import BaseModel
import pytz



# These are unique by id, which is determined by session/track/type
# E.G.: id="Session 1: NLP Applications (Oral)"
class Event(BaseModel):
    id: str
    session: str
    track: str
    type: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    chairs: List[str] = None
    paper_ids: List[str] = None
    link: Optional[str] = None
    room: Optional[str] = None

    @property
    def day(self) -> str:
        pass

    @property
    def time_string(self) -> str:
        pass


class Session(BaseModel):
    id: str
    name: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    events: Dict[str, Event]


class Paper(BaseModel):
    """The content of a paper.

    Needs to be synced with static/js/papers.js and static/js/paper_vis.js.
    """
    id: str
    forum: str
    card_image_path: str
    presentation_id: str
    title: str
    authors: List[str]
    track: str
    paper_type: str
    abstract: str
    tldr: str
    keywords: List[str]
    underline_url: Optional[str] = None
    pdf_url: Optional[str]
    demo_url: Optional[str]
    event_ids: List[str]
    similar_paper_ids: List[str]
    program: str
    material: str = None

    @property
    def rocketchat_channel(self) -> str:
        return f"paper-{self.id.replace('.', '-')}"





class Conference(BaseModel):
    # Time slots, e.g. Session 1
    sessions: Dict[str, Session]
    # All the papers
    papers: Dict[str, Paper]
    # Sessions have events (e.g., Oral session for NLP Applications, or a poster session)
    events: Dict[str, Event]
    