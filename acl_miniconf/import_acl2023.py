from typing import List, Dict, Optional, Union
import logging
import json
import datetime
import re
from pathlib import Path

import yaml
from pydantic import BaseModel
import numpy as np
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


TLDR_LENGTH = 200
DATE_FMT = "%Y-%m-%d %H:%M"

INTERNAL_TO_EXTERNAL_SESSIONS = {
    'Session 3': 'Session 1',
    'Session 4': 'Session 2',
    'Session 5': 'Session 3',
    'Session 6': 'Session 4',
    'Session 8': 'Session 5',
    'Session 9': 'Session 6',
    'Session 10': 'Session 7',
}


def internal_to_external_session(name: str):
    if name in INTERNAL_TO_EXTERNAL_SESSIONS:
        return INTERNAL_TO_EXTERNAL_SESSIONS[name]
    else:
        return name


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


def na_to_none(x):
    if isinstance(x, str):
        return x
    elif np.isnan(x):
        return None
    else:
        return x


def to_underline_paper_id(paper_id: str):
    if paper_id.startswith("P") or paper_id.startswith("C"):
        return paper_id[1:]
    else:
        return paper_id


class Assets(BaseModel):
    underline_paper_id: Optional[str] = None
    underline_id: Optional[int] = None
    poster_preview_png: Optional[str] = None
    poster_pdf: Optional[str] = None
    slides_pdf: Optional[str] = None
    underline_url: Optional[str] = None
    video_url: Optional[str] = None

class AnthologyEntry(BaseModel):
    # Without letter prefix
    paper_id: str
    abstract: str
    # TODO: This is likely the field needed + prefix URL to get Paper PDFs
    file: str
    # TODO: When these are in anthology, use these to link to assets
    attachments: Dict[str, str]


def to_anthology_id(paper_id: str):
    if paper_id.startswith('P'):
        return paper_id[1:]
    else:
        return None

class Acl2023Parser:
    def __init__(
        self,
        *,
        oral_tsv_path: Path,
        poster_tsv_path: Path,
        virtual_tsv_path: Path,
        spotlight_tsv_path: Path,
        extras_xlsx_path: Path,
        acl_main_proceedings_yaml_path: Path
    ):
        self.poster_tsv_path = poster_tsv_path
        self.oral_tsv_path = oral_tsv_path
        self.virtual_tsv_path = virtual_tsv_path
        self.spotlight_tsv_path = spotlight_tsv_path
        self.extras_xlsx_path = extras_xlsx_path
        self.acl_main_proceedings_yaml_path = acl_main_proceedings_yaml_path
        self.anthology_data: Dict[str, AnthologyEntry] = {}
        self.papers: Dict[str, Paper] = {}
        self.sessions: Dict[str, Session] = {}
        self.events: Dict[str, Event] = {}
        self.underline_assets: Dict[str, Assets] = {}
        self.zone = pytz.timezone("America/Toronto")

    def parse(self):
        # Anthology has to be parsed first to fill in abstracts/files/links
        self._add_anthology_data()
        # Underline has to be parsed early to fill in links/files/etc
        self._parse_underline_assets()

        # Parse order intentional, don't change
        self._parse_oral_papers()
        self._parse_poster_papers()
        self._parse_virtual_papers()
        # Order is intentional, spotlight papers also appear in virtual, so repeated papers
        # warnings aren't emitted
        self._parse_spotlight_papers()

        # Parse extra events
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
    
    def _add_anthology_data(self):
        logging.info("Parsing ACL Anthology Data")
        with open(self.acl_main_proceedings_yaml_path) as f:
            entries = yaml.safe_load(f)
        for e in entries:
            self.anthology_data[str(e['id'])] = AnthologyEntry(
                paper_id=str(e['id']),
                abstract=e['abstract'],
                file=e['file'],
                attachments=e['attachments'],
            )
            

    def _parse_underline_assets(self):
        logging.info("Parsing Underline XLSX File")
        df = pd.read_excel(self.extras_xlsx_path, sheet_name="Lectures")
        df = df[df["Paper number"].notnull()]
        for _, paper in df[
            [
                "ID",
                "Paper number",
                "Video file link",
                "Poster URL",
                "Poster document URL",
                "Slideshow URL",
                "Frontend URI",
            ]
        ].iterrows():
            # Underline strips the leading letter, keep in mind
            underline_paper_id = str(paper["Paper number"])
            assets = Assets(
                underline_paper_id=underline_paper_id,
                underline_id=paper["ID"],
                poster_preview_png=na_to_none(paper["Poster URL"]),
                poster_pdf=na_to_none(paper["Poster document URL"]),
                slides_pdf=na_to_none(paper["Slideshow URL"]),
                underline_url=na_to_none(paper["Frontend URI"]),
                video_url=na_to_none(paper["Video file link"]),
            )
            if underline_paper_id in self.underline_assets:
                raise ValueError(
                    f"Repeat paper: {underline_paper_id}\nCurrent: {assets}\nPrior: {self.underline_assets[underline_paper_id]}"
                )
            self.underline_assets[underline_paper_id] = assets

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
        logging.info("Parsing spotlight papers")
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
                    display_name=internal_to_external_session(group_session),
                    start_time=start_dt,
                    end_time=end_dt,
                    type="Paper Sessions",
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
                    underline_paper_id = to_underline_paper_id(paper_id)
                    if underline_paper_id in self.underline_assets:
                        assets = self.underline_assets[underline_paper_id]
                    else:
                        assets = Assets()
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        abstract = self.anthology_data[anthology_id].abstract
                        tldr = abstract[:TLDR_LENGTH] + '...'
                    else:
                        abstract = ""
                        tldr = ""
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        # TODO: group_track
                        track=row.Track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract=abstract,
                        tldr=tldr,
                        event_ids=[event.id],
                        forum="",
                        card_image_path="",
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        slides_pdf=assets.slides_pdf,
                        video_url=assets.video_url,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_virtual_papers(self):
        logging.info("Parsing virtual poster papers")
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
                    display_name=internal_to_external_session(group_session),
                    start_time=start_dt,
                    end_time=end_dt,
                    type="Paper Sessions",
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
                    underline_paper_id = to_underline_paper_id(paper_id)
                    if underline_paper_id in self.underline_assets:
                        assets = self.underline_assets[underline_paper_id]
                    else:
                        assets = Assets()
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        abstract = self.anthology_data[anthology_id].abstract
                        tldr = abstract[:TLDR_LENGTH] + '...'
                    else:
                        abstract = ""
                        tldr = ""
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        track=group_track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract=abstract,
                        tldr=tldr,
                        event_ids=[event.id],
                        similar_paper_ids=[],
                        forum="",
                        card_image_path="",
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        slides_pdf=assets.slides_pdf,
                        video_url=assets.video_url,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_poster_papers(self):
        logging.info("Parsing poster papers")
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
                    display_name=internal_to_external_session(group_session),
                    start_time=start_dt,
                    end_time=end_dt,
                    type="Paper Sessions",
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
                    underline_paper_id = to_underline_paper_id(paper_id)
                    if underline_paper_id in self.underline_assets:
                        assets = self.underline_assets[underline_paper_id]
                    else:
                        assets = Assets()
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        abstract = self.anthology_data[anthology_id].abstract
                        tldr = abstract[:TLDR_LENGTH] + '...'
                    else:
                        abstract = ""
                        tldr = ""
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        track=group_track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract=abstract,
                        tldr=tldr,
                        event_ids=[event.id],
                        forum="",
                        card_image_path="",
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        slides_pdf=assets.slides_pdf,
                        video_url=assets.video_url,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_oral_papers(self):
        logging.info("Parsing oral papers")
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
                    display_name=internal_to_external_session(group_session),
                    start_time=start_dt,
                    end_time=end_dt,
                    type="Paper Sessions",
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
                    underline_paper_id = to_underline_paper_id(paper_id)
                    if underline_paper_id in self.underline_assets:
                        assets = self.underline_assets[underline_paper_id]
                    else:
                        assets = Assets()
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        abstract = self.anthology_data[anthology_id].abstract
                        tldr = abstract[:TLDR_LENGTH] + '...'
                    else:
                        abstract = ""
                        tldr = ""
                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(row.Author),
                        track=group_track,
                        paper_type=row.Length,
                        category=row.Category,
                        abstract=abstract,
                        tldr=tldr,
                        event_ids=[event.id],
                        forum="",
                        card_image_path="",
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        slides_pdf=assets.slides_pdf,
                        video_url=assets.video_url,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_extras_from_spreadsheet(self):
        """Extracts information from the spreadsheet and fills the events that
        were not already extracted from the other TSV files.
        """
        try:
            workbook = load_workbook(filename=self.extras_xlsx_path)
        except FileNotFoundError:
            logging.error(
                f"Could not read spreadsheet from file {self.extras_xlsx_path}. This data won't be added to the program."
            )
            raise
        # Part 1: read all tracks from the spreadsheet
        sheet = workbook["Tracks"]
        spreadsheet_info = dict()
        row = 1
        try:
            while True:
                track_id = sheet["A"][row].value
                track_name = sheet["B"][row].value.strip()
                # Escape slashes, as they break the website
                track_name = track_name.replace("/", "--")
                # Fixing a typo in the original data
                if track_name == "Birds of Fearther":
                    track_name = "Birds of a Feather"
                track = {"id": track_id, "desc": None, "events": defaultdict(list)}
                spreadsheet_info[track_name] = track
                row += 1
        except IndexError:
            # Reached the end of the records
            pass

        # Part 2: assign events to tracks
        sheet = workbook["Event Sessions"]
        row = 1
        # Set the time to our desired timezone. Useful for parsing the dates
        # in the proper locale
        os.environ["TZ"] = "America/Toronto"
        time.tzset()
        try:
            while True:
                track_name = sheet["F"][row].value.strip()
                # Escape slashes, as they break the website
                track_name = track_name.replace("/", "--")
                # Fixing a typo in the original data
                if track_name == "Birds of Fearther":
                    track_name = "Birds of a Feather"
                event_id = sheet["A"][row].value
                event_name = sheet["B"][row].value.strip()
                event_name = event_name.replace("/", "--")
                event_desc = sheet["C"][row].value
                # Parse the start time and end time in UTC
                event_start = sheet["G"][row].value
                event_start = datetime.datetime.strptime(event_start, "%B %d, %Y %H:%M")
                event_end = sheet["H"][row].value
                event_end = datetime.datetime.strptime(event_end, "%B %d, %Y %H:%M")
                # We extract the date from the start date instead of the spreadsheet
                event_date = event_start.date()
                event = {
                    "name": event_name,
                    "desc": event_desc,
                    "date": event_date.isoformat(),
                    "start": event_start.astimezone(
                        pytz.timezone("America/Toronto")
                    ).isoformat(),
                    "end": event_end.astimezone(
                        pytz.timezone("America/Toronto")
                    ).isoformat(),
                }
                spreadsheet_info[track_name]["events"][event_id].append(event)
                row += 1
        except IndexError:
            pass

        self._parse_event_without_papers(spreadsheet_info, "Social", "Socials", MAIN)
        self._parse_event_without_papers(
            spreadsheet_info, "Plenary Sessions", "Plenary Sessions", MAIN
        )
        self._parse_event_without_papers(
            spreadsheet_info, "Workshops", "Workshops", WORKSHOP
        )
        self._parse_multi_event_single_paper(
            spreadsheet_info, "Tutorials", "Tutorials", MAIN
        )
        self._parse_event_without_papers(
            spreadsheet_info, "Findings", "Workshops", FINDINGS
        )
        self._parse_event_without_papers(
            spreadsheet_info, "Industry Track", "Poster", INDUSTRY
        )
        self._parse_event_without_papers(
            spreadsheet_info, "Demo Sessions", "Poster", DEMO
        )
        self._parse_multi_event_single_paper(
            spreadsheet_info, "Coffee Break", "Socials", MAIN
        )
        self._parse_multi_event_single_paper(
            spreadsheet_info, "Diversity and Inclusion", "Workshops", MAIN
        )
        self._parse_multi_event_single_paper(
            spreadsheet_info, "Student Research Workshop", "Workshops", MAIN
        )
        self._parse_multi_event_single_paper(
            spreadsheet_info, "Birds of a Feather", "Socials", MAIN
        )

    def _parse_event_without_papers(
        self, spreadsheet_info, event_key, event_type, program_type, event_name=None
    ):
        for session_key in spreadsheet_info[event_key]["events"]:
            # Single session, single event, single dummy paper
            # We first create the session and store a variable to reference it.
            # Because this Session has a single event, we don't iterate here.
            event_data = spreadsheet_info[event_key]["events"][session_key][0]
            group_session = event_data["name"]
            self.sessions[group_session] = Session(
                id=name_to_id(group_session),
                name=group_session,
                display_name=internal_to_external_session(group_session),
                start_time=event_data["start"],
                end_time=event_data["end"],
                type=event_type,
                events=[],
            )
            session = self.sessions[group_session]
            # This single session has a single event, which we now read.
            # We also use the variable we just declared to add this Event as
            # an event of the Session.
            if event_name is None:
                this_event_name = get_session_event_name(
                    group_session, event_data["name"], event_type
                )
            else:
                this_event_name = event_name
            event_id = name_to_id(this_event_name)
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=session.id,
                    track=event_data["name"],
                    start_time=event_data["start"],
                    end_time=event_data["end"],
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room=None,
                    type=event_type,
                )
            event = self.events[event_id]
            session.events[event_id] = event
            # Finally, we create a single dummy paper with the information of
            # the Event. We then add it to the paper list of the Event above.
            paper_id = f"p_{event_id}"
            dummy_paper = Paper(
                id=paper_id,
                program=program_type,
                title=event_data["name"],
                authors=[],
                track=name_to_id(group_session),
                paper_type=event_type,
                category="",
                abstract=event_data["desc"] if event_data["desc"] is not None else "",
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
            self.papers[paper_id] = dummy_paper
            event.paper_ids.append(paper_id)

    def _parse_multi_event_single_paper(
        self, spreadsheet_info, event_key, event_type, program_type
    ):
        # This is almost the exact same code than _parse_event_without_papers,
        # only with a slightly more complex event handling because a single
        # session has several parallel events.

        # We first create the events. Since the program doesn't separate them
        # in sub-groups, we do it here according to the date.
        all_sessions = set()
        date_to_session = dict()
        for event_session_key in spreadsheet_info[event_key]["events"]:
            for session_event in spreadsheet_info[event_key]["events"][
                event_session_key
            ]:
                all_sessions.add((session_event["start"], session_event["end"]))
        all_sessions = list(all_sessions)
        all_sessions.sort()
        counter = 1
        for session_start, session_end in all_sessions:
            date_to_session[session_start] = f"{event_key} {counter}"
            group_session = f"{event_key} {counter}"
            self.sessions[group_session] = Session(
                id=name_to_id(group_session),
                name=group_session,
                display_name=internal_to_external_session(group_session),
                start_time=session_start,
                end_time=session_end,
                type=event_type,
                events=[],
            )
            counter += 1
        # Now that we know which sessions exist, we can start parsing the schedule
        for event_session_key in spreadsheet_info[event_key]["events"]:
            all_events = spreadsheet_info[event_key]["events"][event_session_key]
            for event in all_events:
                group_session = date_to_session[event["start"]]
                group_track = event["name"]
                event_name = get_session_event_name(
                    group_session, group_track, event_type
                )
                event_id = name_to_id(event_name)
                if event_id not in self.events:
                    self.events[event_id] = Event(
                        id=event_id,
                        session=group_session,
                        track=group_track,
                        start_time=event["start"],
                        end_time=event["end"],
                        chairs=[],
                        paper_ids=[],
                        link=None,
                        room=None,
                        type=event_type,
                    )
                    session = self.sessions[group_session]
                    session.events[event_id] = self.events[event_id]
                    dummy_paper = Paper(
                        id=event_id,
                        program=MAIN,
                        title=event_name,
                        authors=[],
                        track=name_to_id(group_session),
                        paper_type=event_type,
                        category="",
                        abstract="",
                        tldr="",
                        keywords=[],
                        pdf_url="",
                        demo_url="",
                        event_ids=[event_id],
                        similar_paper_ids=[],
                        forum="",
                        card_image_path="",
                        presentation_id="",
                    )
                    self.papers[event_id] = dummy_paper
                    self.events[event_id].paper_ids.append(event_id)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime,)):
            return obj.isoformat()


def main(
    oral_tsv: str = "private_data-acl2023/oral-papers.tsv",
    poster_tsv: str = "private_data-acl2023/poster-demo-papers.tsv",
    virtual_tsv: str = "private_data-acl2023/virtual-papers.tsv",
    spotlight_tsv: str = "private_data-acl2023/spotlight-papers.tsv",
    extras_xlsx: str = "private_data-acl2023/acl-2023-events-export-2023-06-22.xlsx",
    acl_main_proceedings_yaml: str = "private_data-acl2023/main/revised_abstract_papers.yml",
    out_dir: str = "data/acl_2023/data/",
):
    parser = Acl2023Parser(
        oral_tsv_path=Path(oral_tsv),
        poster_tsv_path=Path(poster_tsv),
        virtual_tsv_path=Path(virtual_tsv),
        spotlight_tsv_path=Path(spotlight_tsv),
        extras_xlsx_path=Path(extras_xlsx),
        acl_main_proceedings_yaml_path=Path(acl_main_proceedings_yaml),
    )
    conf = parser.parse()
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True, parents=True)
    conf_dict = conf.dict()

    logging.info("Writing to conference.json")
    with open(out_dir / "conference.json", "w") as f:
        json.dump(conf_dict, f, cls=DateTimeEncoder, sort_keys=True, indent=2)


if __name__ == "__main__":
    typer.run(main)
