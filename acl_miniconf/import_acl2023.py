from typing import List, Dict
import datetime
from pathlib import Path

import pandas as pd
import pytz

from acl_miniconf.data import Session, SessionEvent, Paper, Conference


DATE_FMT = '%Y-%m-%d %H:%M'


def clean_authors(authors: List[str]):
    return [a.strip() for a in authors]

def parse_authors(author_string: str):
    authors = author_string.split(',')
    if len(authors) == 1:
        authors = authors[0].split(' and ')
        return clean_authors(authors)
    else:
        front_authors = authors[:-1]
        last_authors = authors[-1].split(' and ')
        return clean_authors(front_authors + last_authors)


def parse_sessions_and_tracks(df: pd.DataFrame):
    sessions = sorted(set(df.Session.values), key=lambda x: int(x.split()[1]))
    tracks = sorted(set(df.Track.values))
    return sessions, tracks


def get_session_event_name(session: str, track: str, session_type: str):
    return f'{session}: {track} ({session_type})'


class Acl2023Parser:
    def __init__(self, *, oral_tsv_path: Path, poster_tsv_path: Path):
        self.poster_tsv_path = poster_tsv_path
        self.oral_tsv_path = oral_tsv_path
        self.papers: Dict[str, Paper] = {}
        self.sessions: Dict[str, Session] = {}
        self.session_events: Dict[str, SessionEvent] = {}
        self.zone = pytz.timezone('America/Toronto')
    
    def parse(self):
        self._parse_oral_papers(self.oral_tsv_path)
        self._parse_poster_papers(self.poster_tsv_path)
        return Conference(
            sessions=self.sessions,
            papers=self.papers,
            session_events=self.session_events
        )
    
    def _parse_start_end_dt(self, date_str: str, time_str: str):
        start_time, end_time = time_str.split('-')
        start_parsed_dt = self.zone.localize(datetime.datetime.strptime(f'{date_str} {start_time}', DATE_FMT))
        end_parsed_dt = self.zone.localize(datetime.datetime.strptime(f'{date_str} {end_time}', DATE_FMT))
        return start_parsed_dt, end_parsed_dt
    
    def _parse_poster_papers(self, poster_tsv_path: Path):
        df = pd.read_csv(poster_tsv_path, sep='\t')
        group_type = 'Poster'
        for (group_session, group_track), group in df.groupby(['Session', 'Track']):
            group = group.sort_values('Local Order')
            event_name = get_session_event_name(group_session, group_track, group_type)
            start_dt, end_dt = self._parse_start_end_dt(group.iloc[0].Date, group.iloc[0].Time)
            if event_name not in self.session:
                self.sessions[event_name] = SessionEvent(
                    id=event_name,
                    session=group_session,
                    track=group_track,
                    start_time=start_dt,
                    end_time=end_dt,
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room='Poster Session',
                    type=group_type,
                )
            event = self.session_event[event_name]
            if group_session not in self.sessions:
                self.sessions[group_session] = Session(
                    id=group_session,
                    name=group_session,
                    start_time=start_dt,
                    end_time=end_dt,
                    events=[],
                )
            session = self.sessions[group_session]
            if event_name in session.events:
                raise ValueError('Duplicated events')

            session.events[group_session] = event
            for row in group.itertuples():
                paper_id = row.PID
                start_dt, end_dt = self._parse_start_end_dt(row.Date, row.Time)
                event = self.session_events[event_name]
                event.paper_ids.append(paper_id)


    def _parse_oral_papers(self, oral_tsv_path: Path):
        df = pd.read_csv(oral_tsv_path, sep='\t')
        group_type = 'Oral'
        for (group_session, group_track), group in df.groupby(['Session', 'Track']):
            group = group.sort_values('Track Order')
            session_event_name = get_session_event_name(group_session, group_track, group_type)
            start_dt, end_dt = self._parse_start_end_dt(group.iloc[0].Date, group.iloc[0].Time)
            if session_event_name not in self.session_events:
                self.session_events[session_event_name] = SessionEvent(
                    id=session_event_name,
                    track=group_track,
                    start_time=start_dt,
                    end_time=end_dt,
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room=row.Room,
                    type=group_type,
                )
            event = self.session_events[session_event_name]
            if group_session not in self.sessions:
                self.sessions[group_session] = Session(
                    id=group_session,
                    name=group_session,
                    start_time=start_dt,
                    end_time=end_dt,
                    events=[],
                )
            session = self.sessions[group_session]
            session.events.append(event)
            for row in group.itertuples():
                paper_id = row.PID
                event.paper_ids.append(paper_id)
                paper = Paper(
                    id=paper_id,
                    program='Main',
                    title=row.Title,
                    authors=parse_authors(row.Author),
                    track=group_track,
                    paper_type=row.Length,
                    abstract="",
                    tldr="",
                    keywords=[],
                    pdf_url="",
                    demo_url="",
                    session_event_ids=[event.id],
                    similar_paper_ids=[],
                    program="",
                    forum="",
                    card_image_path="",
                    presentation_id="",
                )
                if row.PID in self.papers:
                    raise ValueError('Duplicate papers')
                self.papers[row.PID] = paper
