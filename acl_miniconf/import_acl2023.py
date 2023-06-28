from typing import List, Dict
import logging
import pickle
import json
import datetime
from pathlib import Path

import yaml
import typer
import pandas as pd
import pytz
from rich.logging import RichHandler

import os
import time
from collections import defaultdict
from openpyxl import load_workbook

from acl_miniconf.data import (
    Session,
    Event,
    Paper,
    Conference,
    MAIN,
    WORKSHOP,
    FINDINGS,
    DEMO,
    INDUSTRY,
    PROGRAMS,
    name_to_id,
)

logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[RichHandler(rich_tracebacks=True)],
    force=True,
)


DATE_FMT = "%Y-%m-%d %H:%M"


def clean_authors(authors: List[str]):
    return [a.strip() for a in authors]


def parse_authors(author_string: str):
    authors = author_string.split(",")
    if len(authors) == 1:
        authors = authors[0].split(" and ")
        return clean_authors(authors)
    else:
        front_authors = authors[:-1]
        last_authors = authors[-1].split(" and ")
        return clean_authors(front_authors + last_authors)


def parse_sessions_and_tracks(df: pd.DataFrame):
    sessions = sorted(set(df.Session.values), key=lambda x: int(x.split()[1]))
    tracks = sorted(set(df.Track.values))
    return sessions, tracks


def get_session_event_name(session: str, track: str, session_type: str):
    return f"{session}: {track} ({session_type})"


def determine_program(category: str):
    if category in ["CL", "TACL", "Main-Oral", "Main-Poster"]:
        return MAIN
    elif category == "Findings":
        return FINDINGS
    elif category == "Demo":
        return DEMO
    elif category in ["Workshop", "SRW"]:
        return WORKSHOP
    elif category == "Industry":
        return INDUSTRY
    else:
        raise ValueError(f"Could not determine program from: {category}")


class Acl2023Parser:
    def __init__(
        self,
        *,
        oral_tsv_path: Path,
        poster_tsv_path: Path,
        virtual_tsv_path: Path,
        spotlight_tsv_path: Path,
        extras_xlsx_path: Path
    ):
        self.poster_tsv_path = poster_tsv_path
        self.oral_tsv_path = oral_tsv_path
        self.virtual_tsv_path = virtual_tsv_path
        self.spotlight_tsv_path = spotlight_tsv_path
        self.extras_xlsx_path = extras_xlsx_path
        self.papers: Dict[str, Paper] = {}
        self.sessions: Dict[str, Session] = {}
        self.events: Dict[str, Event] = {}
        self.zone = pytz.timezone("America/Toronto")

    def parse(self):
        self._parse_oral_papers()
        self._parse_poster_papers()
        self._parse_virtual_papers()
        # Order is intentional, spotlight papers also appear in virtual, so repeated papers
        # warnings aren't emitted
        self._parse_spotlight_papers()
        self._parse_extras_from_spreadsheet()
        self.validate()
        return Conference(
            sessions=self.sessions,
            papers=self.papers,
            events=self.events,
        )

    def validate(self):
        for p in self.papers.values():
            assert len(p.event_ids) > 0
            assert p.program in PROGRAMS

    def _parse_start_end_dt(self, date_str: str, time_str: str):
        start_time, end_time = time_str.split("-")
        start_parsed_dt = self.zone.localize(
            datetime.datetime.strptime(f"{date_str} {start_time}", DATE_FMT)
        )
        end_parsed_dt = self.zone.localize(
            datetime.datetime.strptime(f"{date_str} {end_time}", DATE_FMT)
        )
        return start_parsed_dt, end_parsed_dt

    def _parse_spotlight_papers(self):
        df = pd.read_csv(self.spotlight_tsv_path, sep="\t")
        df = df[df.PID.notnull()]
        group_type = "Spotlight"
        # start_dt and end_dt are not in the sheets, but hardcoded instead
        start_dt = self.zone.localize(
            datetime.datetime(year=2023, month=7, day=10, hour=19, minute=0)
        )
        end_dt = self.zone.localize(
            datetime.datetime(year=2023, month=7, day=10, hour=21, minute=0)
        )
        # TODO: Fix Session once the sheet has it
        for group_room, group in df.groupby(["Room"]):
            group_session = "Spotlight"
            group = group.sort_values("Local order")
            room = group.iloc[0].Room
            group_track = "Spotlight"
            # There are multiple concurrent spotlight events, each in a different room.
            # Thus, the one spotlight session should have multiple events that are differentiated by room
            event_name = get_session_event_name(group_session, group_room, group_type)
            event_id = name_to_id(event_name)

            # TODO: Add back date/time when the sheet has it
            # start_dt, end_dt = self._parse_start_end_dt(
            #    group.iloc[0].Date, group.iloc[0].Time
            # )
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=group_session,
                    track=group_track,
                    start_time=start_dt,
                    end_time=end_dt,
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room=room,
                    type=group_type,
                )
            event = self.events[event_id]
            if group_session not in self.sessions:
                self.sessions[group_session] = Session(
                    id=name_to_id(group_session),
                    name=group_session,
                    start_time=start_dt,
                    end_time=end_dt,
                    events=[],
                )
            session = self.sessions[group_session]
            session.events[event_id] = event
            for row in group.itertuples():
                paper_id = row.PID
                event.paper_ids.append(paper_id)
                if row.PID in self.papers:
                    paper = self.papers[row.PID]
                    if event.id not in paper.event_ids:
                        paper.event_ids.append(event.id)
                else:
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        # TODO: group_track
                        track=row.Track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract="",
                        tldr="",
                        keywords=[],
                        pdf_url="",
                        demo_url="",
                        event_ids=[event.id],
                        similar_paper_ids=[],
                        forum="",
                        card_image_path="",
                        presentation_id="",
                    )
                    self.papers[row.PID] = paper

    def _parse_virtual_papers(self):
        df = pd.read_csv(self.virtual_tsv_path, sep="\t")
        df = df[df.PID.notnull()]
        group_type = "Virtual Poster"
        for (group_session, group_track), group in df.groupby(["Session", "Track"]):
            group = group.sort_values("Local order")
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            start_dt, end_dt = self._parse_start_end_dt(
                group.iloc[0].Date, group.iloc[0].Time
            )
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=group_session,
                    track=group_track,
                    start_time=start_dt,
                    end_time=end_dt,
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room="Virtual Poster Session",
                    type=group_type,
                )
            event = self.events[event_id]
            if group_session not in self.sessions:
                self.sessions[group_session] = Session(
                    id=name_to_id(group_session),
                    name=group_session,
                    start_time=start_dt,
                    end_time=end_dt,
                    events=[],
                )
            session = self.sessions[group_session]
            if event_id in session.events:
                raise ValueError("Duplicated events")
            session.events[event_id] = event

            for row in group.itertuples():
                paper_id = row.PID
                start_dt, end_dt = self._parse_start_end_dt(row.Date, row.Time)
                event = self.events[event_id]
                event.paper_ids.append(paper_id)
                if row.PID in self.papers:
                    logging.warning(
                        f"Duplicate papers in virtual: {row.PID}\nExisting: {self.papers[row.PID]}\nNew:{paper}"
                    )
                    paper = self.papers[row.PID]
                    if event.id not in paper.event_ids:
                        paper.event_ids.append(event.id)
                else:
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        track=group_track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract="",
                        tldr="",
                        keywords=[],
                        pdf_url="",
                        demo_url="",
                        event_ids=[event.id],
                        similar_paper_ids=[],
                        forum="",
                        card_image_path="",
                        presentation_id="",
                    )
                    self.papers[row.PID] = paper

    def _parse_poster_papers(self):
        df = pd.read_csv(self.poster_tsv_path, sep="\t")
        df = df[df.PID.notnull()]
        group_type = "Poster"
        for (group_session, group_track), group in df.groupby(["Session", "Track"]):
            group = group.sort_values("Local order")
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            start_dt, end_dt = self._parse_start_end_dt(
                group.iloc[0].Date, group.iloc[0].Time
            )
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=group_session,
                    track=group_track,
                    start_time=start_dt,
                    end_time=end_dt,
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room="Poster Session",
                    type=group_type,
                )
            event = self.events[event_id]

            if group_session not in self.sessions:
                self.sessions[group_session] = Session(
                    id=name_to_id(group_session),
                    name=group_session,
                    start_time=start_dt,
                    end_time=end_dt,
                    events=[],
                )
            session = self.sessions[group_session]
            if event_id in session.events:
                raise ValueError("Duplicated events")
            session.events[event_id] = event

            for row in group.itertuples():
                paper_id = row.PID
                start_dt, end_dt = self._parse_start_end_dt(row.Date, row.Time)
                event = self.events[event_id]
                event.paper_ids.append(paper_id)
                if row.PID in self.papers:
                    logging.warning(
                        f"Duplicate papers in posters: {row.PID}\n{self.papers[row.PID]}"
                    )
                    paper = self.papers[row.PID]
                    if event.id not in paper.event_ids:
                        paper.event_ids.append(event.id)
                else:
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        track=group_track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract="",
                        tldr="",
                        keywords=[],
                        pdf_url="",
                        demo_url="",
                        event_ids=[event.id],
                        similar_paper_ids=[],
                        forum="",
                        card_image_path="",
                        presentation_id="",
                    )
                    self.papers[row.PID] = paper

    def _parse_oral_papers(self):
        df = pd.read_csv(self.oral_tsv_path, sep="\t")
        df = df[df.PID.notnull()]
        group_type = "Oral"
        for (group_session, group_track), group in df.groupby(["Session", "Track"]):
            group = group.sort_values("Track Order")
            room = group.iloc[0].Room
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            start_dt, end_dt = self._parse_start_end_dt(
                group.iloc[0].Date, group.iloc[0].Time
            )
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=group_session,
                    track=group_track,
                    start_time=start_dt,
                    end_time=end_dt,
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room=room,
                    type=group_type,
                )
            event = self.events[event_id]
            if group_session not in self.sessions:
                self.sessions[group_session] = Session(
                    id=name_to_id(group_session),
                    name=group_session,
                    start_time=start_dt,
                    end_time=end_dt,
                    events=[],
                )
            session = self.sessions[group_session]
            session.events[event_id] = event
            for row in group.itertuples():
                paper_id = row.PID
                event.paper_ids.append(paper_id)
                if row.PID in self.papers:
                    logging.warning(
                        f"Duplicate papers in oral: {row.PID}\n{self.papers[row.PID]}"
                    )
                    paper = self.papers[row.PID]
                    if event.id not in paper.event_ids:
                        paper.event_ids.append(event.id)
                else:
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        track=group_track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract="",
                        tldr="",
                        keywords=[],
                        pdf_url="",
                        demo_url="",
                        event_ids=[event.id],
                        similar_paper_ids=[],
                        forum="",
                        card_image_path="",
                        presentation_id="",
                    )
                    self.papers[row.PID] = paper

    def _parse_extras_from_spreadsheet(self):
        """ Extracts information from the spreadsheet and fills the events that
        were not already extracted from the other TSV files.
        """
        try:
            workbook = load_workbook(filename=self.extras_xlsx_path)
        except FileNotFoundError:
            logging.error(
                f"Could not read spreadsheet from file {self.extras_xlsx_path}. This data won't be added to the program."
            )
            return
        # Part 1: read all tracks from the spreadsheet
        sheet = workbook['Tracks']
        spreadsheet_info = dict()
        row = 1
        try:
            while True:
                track_id = sheet['A'][row].value
                track_name = sheet['B'][row].value.strip()
                track = {'id': track_id,
                         'desc': None,
                         'events': defaultdict(list)}
                spreadsheet_info[track_name] = track
                row += 1
        except IndexError:
            # Reached the end of the records
            pass

        # Part 2: assign events to tracks
        sheet = workbook['Event Sessions']
        row = 1
        # Set the time to our desired timezone. Useful for parsing the dates
        # in the proper locale
        os.environ['TZ'] = 'America/Toronto'
        time.tzset()
        try:
            while True:
                track_name = sheet['F'][row].value.strip()
                event_id = sheet['A'][row].value
                event_name = sheet['B'][row].value.strip()
                event_desc = sheet['C'][row].value
                # Parse the start time and end time in UTC
                event_start = sheet['G'][row].value
                event_start = datetime.datetime.strptime(event_start, '%B %d, %Y %H:%M')
                event_end = sheet['H'][row].value
                event_end = datetime.datetime.strptime(event_end, '%B %d, %Y %H:%M')
                # We extract the date from the start date instead of the spreadsheet
                event_date = event_start.date()
                event = {'name': event_name,
                         'desc': event_desc,
                         'date': event_date.isoformat(),
                         'start': event_start.astimezone(pytz.timezone('America/Toronto')).isoformat(),
                         'end': event_end.astimezone(pytz.timezone('America/Toronto')).isoformat()}
                spreadsheet_info[track_name]['events'][event_id].append(event)
                row += 1
        except IndexError:
            pass

        self._parse_socials(spreadsheet_info)
        self._parse_tutorials(spreadsheet_info)
        self._parse_plenaries(spreadsheet_info)

    def _parse_socials(self, spreadsheet_info):
        id_social = 'Social'
        group_type = "Social Event"
        for social_event_key in spreadsheet_info[id_social]['events']:
            # A social event is a session with a single event.
            social_event = spreadsheet_info[id_social]['events'][social_event_key][0]
            group_session = social_event['name']
            self.sessions[group_session] = Session(
                id=name_to_id(group_session),
                name=group_session,
                start_time=social_event['start'],
                end_time=social_event['end'],
                events=[]
            )
            session = self.sessions[group_session]

            group_track = social_event['name']
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=group_session,
                    track=group_track,
                    start_time=social_event['start'],
                    end_time=social_event['end'],
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room=None,
                    type=group_type,
                )
            event = self.events[event_id]
            session.events[event_id] = event

    def _parse_tutorials(self, spreadsheet_info):
        id_tutorials = 'Tutorials'
        group_type = "Tutorial"
        # We first create the events. Since the program doesn't separate the
        # tutorials in sub-groups, we do it here according to the date.
        all_sessions = set()
        date_to_session = dict()
        for tutorial_key in spreadsheet_info[id_tutorials]['events']:
            for tutorial_event in spreadsheet_info[id_tutorials]['events'][tutorial_key]:
                all_sessions.add((tutorial_event['start'], tutorial_event['end']))
        all_sessions = list(all_sessions)
        all_sessions.sort()
        counter = 1
        for session_start, session_end in all_sessions:
            date_to_session[session_start] = f'Tutorials {counter}'
            group_session = f'Tutorials {counter}'
            self.sessions[group_session] = Session(
                id=name_to_id(group_session),
                name=group_session,
                start_time=session_start,
                end_time=session_end,
                events=[]
            )
            counter += 1
        # Now that we know which sessions exist, we can start parsing the schedule
        for tutorial_key in spreadsheet_info[id_tutorials]['events']:
            tutorial_events = spreadsheet_info[id_tutorials]['events'][tutorial_key]
            for event in tutorial_events:
                group_session = date_to_session[event['start']]
                group_track = event['name']
                event_name = get_session_event_name(group_session, group_track, group_type)
                event_id = name_to_id(event_name)
                if event_id not in self.events:
                    self.events[event_id] = Event(
                        id=event_id,
                        session=group_session,
                        track=group_track,
                        start_time=event['start'],
                        end_time=event['end'],
                        chairs=[],
                        paper_ids=[],
                        link=None,
                        room=None,
                        type=group_type,
                    )
                    session = self.sessions[group_session]
                    session.events[event_id] = self.events[event_id]

    def _parse_plenaries(self, spreadsheet_info):
        id_plenary = 'Plenary Sessions'
        group_type = "Plenary Session"
        for plenary_key in spreadsheet_info[id_plenary]['events']:
            # A social event is a session with a single event.
            plenary_event = spreadsheet_info[id_plenary]['events'][plenary_key][0]
            group_session = plenary_event['name']
            self.sessions[group_session] = Session(
                id=name_to_id(group_session),
                name=group_session,
                start_time=plenary_event['start'],
                end_time=plenary_event['end'],
                events=[]
            )

            session = self.sessions[group_session]
            group_track = plenary_event['name']
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=group_session,
                    track=group_track,
                    start_time=plenary_event['start'],
                    end_time=plenary_event['end'],
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room=None,
                    type=group_type,
                )
            event = self.events[event_id]
            session.events[event_id] = event


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime,)):
            return obj.isoformat()


def main(
    oral_tsv: str = "private_data-acl2023/oral-papers.tsv",
    poster_tsv: str = "private_data-acl2023/poster-demo-papers.tsv",
    virtual_tsv: str = "private_data-acl2023/virtual-papers.tsv",
    spotlight_tsv: str = "private_data-acl2023/spotlight-papers.tsv",
    extras_xlsx : str = "private_data-acl2023/acl-2023-events-export-2023-06-22.xlsx",
    out_dir: str = "data/acl_2023/data/",
):
    parser = Acl2023Parser(
        oral_tsv_path=Path(oral_tsv),
        poster_tsv_path=Path(poster_tsv),
        virtual_tsv_path=Path(virtual_tsv),
        spotlight_tsv_path=Path(spotlight_tsv),
        extras_xlsx_path=Path(extras_xlsx)
    )
    conf = parser.parse()
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True, parents=True)
    conf_dict = conf.dict()

    with open(out_dir / "conference.json", "w") as f:
        json.dump(conf_dict, f, cls=DateTimeEncoder)


if __name__ == "__main__":
    typer.run(main)
