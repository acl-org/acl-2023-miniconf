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
    PLENARIES,
    TUTORIALS,
    WORKSHOPS,
    Session,
    Event,
    Paper,
    Conference,
    Workshop,
    Tutorial,
    Plenary,
    MAIN,
    WORKSHOP,
    FINDINGS,
    DEMO,
    INDUSTRY,
    PROGRAMS,
    name_to_id,
    AnthologyAuthor,
)
from acl_miniconf.import_booklet_acl2023 import Booklet

logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[RichHandler(rich_tracebacks=True)],
    force=True,
)


TLDR_LENGTH = 300
DATE_FMT = "%Y-%m-%d %H:%M"

# These should be skipped, eg plenaries in the booklet where
# the booklet has more information (e.g., abstracts)
UNDERLINE_EVENTS_TO_SKIP = {
    # Plenaries
    "15192",
    "15244",
    "15246",
    "15270",
    "15247",
    "15247",  # Ethics Panel, which is a duplicate
    # Spotlights
    "15510",
    "15511",
    "15221",
}



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


def fix_col_names(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(
        columns={
            "Start Time": "Start_Time",
            "End Time": "End_Time",
        }
    )


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
    # TODO: Post-conference, set this to anthology video
    video_url: Optional[str] = None


class AnthologyEntry(BaseModel):
    # Without letter prefix
    paper_id: str
    anthology_id: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    # TODO: This is likely the field needed + prefix URL to get Paper PDFs
    file: Optional[str] = None
    # TODO: When these are in anthology, use these to link to assets
    attachments: Dict[str, str] = {}
    authors: List[AnthologyAuthor] = []


class Keywords(BaseModel):
    paper_id: str
    track: str
    keywords: List[str] = []
    languages: List[str] = []


def to_anthology_id(paper_id: str):
    if paper_id.startswith("P"):
        return paper_id[1:]
    elif paper_id.startswith("D") or paper_id.startswith('I') or paper_id.startswith("S"):
        return paper_id
    else:
        return None


def clean_authors(authors: List[str]):
    return [a.strip() for a in authors]


def parse_authors(
    anthology_data: Dict[str, AnthologyEntry], paper_id: str, author_string: str
) -> List[str]:
    anthology_id = to_anthology_id(paper_id)
    if anthology_id is None:
        authors = author_string.split(",")
        if len(authors) == 1:
            authors = authors[0].split(" and ")
            return clean_authors(authors)
        else:
            front_authors = authors[:-1]
            last_authors = authors[-1].split(" and ")
            return clean_authors(front_authors + last_authors)
    else:
        authors = []
        for a in anthology_data[anthology_id].authors:
            authors.append(a.name)
        return authors


def underline_paper_id_to_sheets_id(paper_id: Union[str, int]) -> str:
    if isinstance(paper_id, int):
        return str(paper_id)
    elif paper_id.startswith('demo-'):
        return 'D' + paper_id[5:]
    elif paper_id.startswith('srw-'):
        return 'S' + paper_id[4:]
    elif paper_id.startswith('industry-'):
        return 'I' + paper_id[9:]
    else:
        return paper_id


class Acl2023Parser:
    def __init__(
        self,
        *,
        oral_tsv_path: Path,
        poster_tsv_path: Path,
        virtual_tsv_path: Path,
        spotlight_tsv_path: Path,
        extras_xlsx_path: Path,
        acl_main_long_proceedings_yaml_path: Path,
        acl_main_short_proceedings_yaml_path: Path,
        acl_main_findings_proceedings_yaml_path: Path,
        acl_demo_proceedings_yaml_path: Path,
        acl_industry_proceedings_yaml_path: Path,
        acl_srw_proceedings_yaml_path: Path,
        workshop_papers_yaml_path: Path,
        workshops_yaml_path: Path,
        booklet_json_path: Path,
        socials_json_path: Path,
        keywords_csv_path: Path,
        acl_anthology_prefix: str,
    ):
        self.poster_tsv_path = poster_tsv_path
        self.oral_tsv_path = oral_tsv_path
        self.virtual_tsv_path = virtual_tsv_path
        self.spotlight_tsv_path = spotlight_tsv_path
        self.extras_xlsx_path = extras_xlsx_path
        self.acl_main_long_proceedings_yaml_path = acl_main_long_proceedings_yaml_path
        self.acl_main_short_proceedings_yaml_path = acl_main_short_proceedings_yaml_path
        self.acl_main_findings_proceedings_yaml_path = acl_main_findings_proceedings_yaml_path
        self.acl_demo_proceedings_yaml_path = acl_demo_proceedings_yaml_path
        self.acl_industry_proceedings_yaml_path = acl_industry_proceedings_yaml_path
        self.acl_srw_proceedings_yaml_path = acl_srw_proceedings_yaml_path
        self.workshop_papers_yaml_path = workshop_papers_yaml_path
        self.workshops_yaml_path = workshops_yaml_path
        self.booklet_json_path = booklet_json_path
        self.socials_json_path = socials_json_path
        self.keywords_csv_path = keywords_csv_path
        self.acl_anthology_prefix = acl_anthology_prefix
        self.booklet: Booklet = Booklet.from_booklet_data(
            booklet_json_path, workshops_yaml_path
        )
        self.anthology_data: Dict[str, AnthologyEntry] = {}
        self.papers: Dict[str, Paper] = {}
        self.sessions: Dict[str, Session] = {}
        self.events: Dict[str, Event] = {}
        self.tutorials: Dict[str, Tutorial] = {}
        self.plenaries: Dict[str, Plenary] = {}
        self.underline_assets: Dict[str, Assets] = {}
        self.zone = pytz.timezone("America/Toronto")
        self.workshops: Dict[str, Workshop] = {}
        self.keywords: Dict[str, Keywords] = {}
        self.spreadsheet_info: Dict = {}

    def parse(self):
        # Anthology has to be parsed first to fill in abstracts/files/links
        self._add_anthology_data()
        # Underline has to be parsed early to fill in links/files/etc
        self._parse_underline_assets()
        self._parse_underline_spreadsheet()
        self._parse_keywords()
        # Early parse special sessions, so they can be filled in
        self._parse_workshops()
        self._parse_plenaries()
        self._parse_tutorials()

        # Parse order intentional, don't change
        self._parse_oral_papers()
        self._parse_poster_papers()
        self._parse_virtual_papers()
        # Order is intentional, spotlight papers also appear in virtual, so repeated papers
        # warnings aren't emitted
        self._parse_spotlight_papers()

        # Parse extra events
        self._parse_extras_from_spreadsheet(self.socials_json_path)

        self._parse_workshop_papers()

        self.validate()
        return Conference(
            sessions=self.sessions,
            papers=self.papers,
            events=self.events,
            workshops=self.workshops,
            plenaries=self.plenaries,
            tutorials=self.tutorials,
        )

    def validate(self):
        for p in self.papers.values():
            # TODO: Remove check once associate workshop papers with event
            if p.program != WORKSHOP:
                assert len(p.event_ids) > 0
            assert p.program in PROGRAMS

        for e in self.events.values():
            assert not isinstance(e, Plenary)
            assert not isinstance(e, Tutorial)
            assert not isinstance(e, Workshop)
    
    def get_anthology_urls(self, paper_type: str, paper_length: str, anthology_publication_id: str):
        if paper_type == 'demo':
            anthology_url = self.acl_anthology_prefix + f"2023.acl-demo.{anthology_publication_id}"
            paper_pdf = self.acl_anthology_prefix + f"2023.acl-demo.{anthology_publication_id}.pdf"
        elif paper_type == 'industry':
            anthology_url = self.acl_anthology_prefix + f"2023.acl-industry.{anthology_publication_id}"
            paper_pdf = self.acl_anthology_prefix + f"2023.acl-industry.{anthology_publication_id}.pdf"
        elif paper_type == 'srw':
            anthology_url = self.acl_anthology_prefix + f"2023.acl-srw.{anthology_publication_id}"
            paper_pdf = self.acl_anthology_prefix + f"2023.acl-srw.{anthology_publication_id}.pdf"
        elif paper_type == 'findings':
            anthology_url = self.acl_anthology_prefix + f"2023.findings-acl.{anthology_publication_id}"
            paper_pdf = self.acl_anthology_prefix + f"2023.findings-acl.{anthology_publication_id}.pdf"
        else:
            anthology_url = self.acl_anthology_prefix + f"2023.acl-{paper_length}.{anthology_publication_id}"
            paper_pdf = self.acl_anthology_prefix + f"2023.acl-{paper_length}.{anthology_publication_id}.pdf"
        return anthology_url, paper_pdf
    
    def _parse_keywords(self):
        df = pd.read_csv('data/acl_2023/data/keywords.csv', sep=',').fillna("")
        for _, r in df.iterrows():
            submission_id = r['Submission ID']
            paper_id = f'P{submission_id}'
            track = r['Track']
            assert len(track) != 0
            if r['Keywords'] == "":
                keywords = []
            else:
                keywords = r['Keywords'].split("|")
            if r['Languages'] == "":
                languages = []
            else:
                languages = r['Languages'].split("|")

            self.keywords[paper_id] = Keywords(
                paper_id=paper_id,
                track=track,
                keywords=keywords,
                languages=languages,
            )

    def _parse_tutorials(self):
        self.tutorials = self.booklet.tutorials
        for t in self.tutorials.values():
            t.anthology_url = self.acl_anthology_prefix + f"2023.acl-tutorials.{t.id[1:]}"
            t.tutorial_pdf = self.acl_anthology_prefix + f"2023.acl-tutorials.{t.id[1:]}.pdf"

        for session in self.booklet.tutorial_sessions.values():
            if session.id in self.sessions:
                raise ValueError("Duplicate tutorial session")
            self.sessions[session.id] = session

    def _parse_plenaries(self):
        self.plenaries = self.booklet.plenaries
        for session in self.booklet.plenary_sessions.values():
            if session.id in self.sessions:
                raise ValueError("Duplicate plenary session")
            self.sessions[session.id] = session

    def _parse_workshops(self):
        self.workshops = self.booklet.workshops
        for session in self.booklet.workshop_sessions.values():
            if session.id in self.sessions:
                raise ValueError("Duplicate workshop session")
            self.sessions[session.id] = session

    def _parse_workshop_papers(self):
        logging.info("Parsing workshop papers")
        with open(self.workshop_papers_yaml_path) as f:
            papers = yaml.safe_load(f)
        workshop_papers: List[Paper] = []
        for p in papers:
            workshop_papers.append(Paper(**p))

        for p in workshop_papers:
            self.papers[p.id] = p

    def _add_anthology_data(self):
        logging.info("Parsing ACL Anthology main track data")
        entries = []
        with open(self.acl_main_long_proceedings_yaml_path) as f:
            entries.extend(yaml.safe_load(f))

        with open(self.acl_main_short_proceedings_yaml_path) as f:
            entries.extend(yaml.safe_load(f))

        with open(self.acl_main_findings_proceedings_yaml_path) as f:
            entries.extend(yaml.safe_load(f))

        for e in entries:
            self.anthology_data[str(e["id"])] = AnthologyEntry(
                paper_id=str(e["id"]),
                anthology_id=str(e['anthology_id']),
                abstract=e["abstract"],
                file=e["file"],
                attachments=e["attachments"],
                authors=[
                    AnthologyAuthor(
                        first_name=a["first_name"],
                        middle_name=a["middle_name"],
                        last_name=a["last_name"],
                        semantic_scholar=a["semantic_scholar"],
                        google_scholar=a["google_scholar"],
                    )
                    for a in e["authors"]
                ],
            )
        logging.info("Parsing ACL Anthology demo track data")
        with open(self.acl_demo_proceedings_yaml_path) as f:
            entries = yaml.safe_load(f)
        for idx, e in enumerate(entries, start=1):
            self.anthology_data[str(e["id"])] = AnthologyEntry(
                # These are prefixed with D already
                paper_id=str(e["id"]),
                anthology_id=str(idx),
                abstract=e["abstract"],
                file=e["file"],
                authors=[
                    AnthologyAuthor(
                        first_name=a["first_name"],
                        last_name=a["last_name"],
                    )
                    for a in e["authors"]
                ],
            )

        logging.info("Parsing ACL Anthology industry track data")
        with open(self.acl_industry_proceedings_yaml_path) as f:
            entries = yaml.safe_load(f)
        for idx, e in enumerate(entries, start=1):
            paper_id = 'I' + str(e['id'])
            self.anthology_data[paper_id] = AnthologyEntry(
                # These are not prexied with I already
                paper_id=paper_id,
                anthology_id=str(idx),
                abstract=e["abstract"],
                file=e["file"],
                authors=[
                    AnthologyAuthor(
                        first_name=a["first_name"],
                        last_name=a["last_name"],
                    )
                    for a in e["authors"]
                ],
            )

        logging.info("Parsing ACL Anthology SRW track data")
        with open(self.acl_srw_proceedings_yaml_path) as f:
            entries = yaml.safe_load(f)
        for idx, e in enumerate(entries, start=1):
            paper_id = 'S' + str(e['id'])
            self.anthology_data[paper_id] = AnthologyEntry(
                # These are not prexied with I already
                paper_id=paper_id,
                anthology_id=str(idx),
                abstract=e["abstract"],
                file=e["file"],
                authors=[
                    AnthologyAuthor(
                        first_name=a["first_name"],
                        last_name=a["last_name"],
                    )
                    for a in e["authors"]
                ],
            )

    def _parse_underline_assets(self):
        logging.info("Parsing Underline XLSX File")
        df = pd.read_excel(self.extras_xlsx_path, sheet_name="Lectures")
        df = df[df["Paper number"].notnull()]
        df['Paper number'] = df['Paper number'].map(underline_paper_id_to_sheets_id)
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
            underline_paper_id = paper["Paper number"]
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

    def _parse_start_end_dt(self, date_str: str, start_time: str, end_time: str):
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
        # Industry papers are missing their track
        df.loc[df.Category == "Industry", "Track"] = "Industry"
        df = fix_col_names(df[df.PID.notnull()])
        group_type = "Spotlight"
        # start_dt and end_dt are not in the sheets, but hardcoded instead
        start_dt = self.zone.localize(
            datetime.datetime(year=2023, month=7, day=10, hour=19, minute=0)
        )
        end_dt = self.zone.localize(
            datetime.datetime(year=2023, month=7, day=10, hour=21, minute=0)
        )
        for (group_session, group_room), group in df.groupby(["Session", "Location"]):
            group = group.sort_values("Presentation Order")
            # There are multiple concurrent spotlight events, each in a different room.
            # Thus, the one spotlight session should have multiple events that are differentiated by room
            track = f'Spotlight - {group_room}'
            event_name = get_session_event_name(group_session, track, group_type)
            event_id = name_to_id(event_name)

            start_dt, end_dt = self._parse_start_end_dt(
                group.iloc[0].Date,
                group.iloc[0]["Start_Time"],
                group.iloc[0]["End_Time"],
            )
            if event_id not in self.events:
                self.events[event_id] = Event(
                    id=event_id,
                    session=group_session,
                    track=track,
                    start_time=start_dt,
                    end_time=end_dt,
                    chairs=[],
                    paper_ids=[],
                    link=None,
                    room=group_room,
                    type=group_type,
                )
            event = self.events[event_id]
            if group_session not in self.sessions:
                self.sessions[group_session] = Session(
                    id=name_to_id(group_session),
                    name=group_session,
                    display_name=group_session,
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
                    if row.Category == 'Demo':
                        paper_type = 'demo'
                    elif row.Category == 'Industry':
                        paper_type = 'industry'
                    elif row.Category == 'SRW':
                        paper_type = 'srw'
                    elif row.Category == 'Findings':
                        paper_type = 'findings'
                    else:
                        paper_type = row.Category

                    # This is the internal ID, but in the anthology format, distinct from the anthology_id used for publication
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        anthology_entry = self.anthology_data[anthology_id]
                        abstract = anthology_entry.abstract
                        tldr = abstract[:TLDR_LENGTH] + "..."
                        anthology_publication_id = anthology_entry.anthology_id
                        if anthology_publication_id is None:
                            anthology_url = None
                            paper_pdf = None
                        else:
                            anthology_url, paper_pdf = self.get_anthology_urls(paper_type, row.Length, anthology_publication_id)
                    else:
                        abstract = ""
                        tldr = ""
                        anthology_url = None
                        paper_pdf = None

                    if paper_id in self.keywords:
                        kw = self.keywords[paper_id]
                        keywords = kw.keywords
                        languages = kw.languages
                    else:
                        keywords = []
                        languages = []

                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(
                            self.anthology_data, paper_id, row.Author
                        ),
                        track=track,
                        display_track=row.Track,
                        paper_type=paper_type,
                        category=row.Category,
                        abstract=abstract,
                        keywords=keywords,
                        languages=languages,
                        tldr=tldr,
                        event_ids=[event.id],
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        anthology_url=anthology_url,
                        paper_pdf=paper_pdf,
                        slides_pdf=assets.slides_pdf,
                        video_url=assets.video_url,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_virtual_papers(self):
        logging.info("Parsing virtual poster papers")
        df = pd.read_csv(self.virtual_tsv_path, sep="\t")
        # Industry papers are missing their track
        df.loc[df.Category == "Industry", "Track"] = "Industry"
        df = fix_col_names(df[df.PID.notnull()])
        group_type = "Virtual Poster"
        for (group_session, group_track), group in df.groupby(["Session", "Track"]):
            group = group.sort_values("Presentation Order")
            assert len(set(group.Location.values)) == 1
            room = group.iloc[0].Location
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            start_dt, end_dt = self._parse_start_end_dt(
                group.iloc[0].Date,
                group.iloc[0]["Start_Time"],
                group.iloc[0]["End_Time"],
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
                    display_name=group_session,
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
                start_dt, end_dt = self._parse_start_end_dt(
                    row.Date, row.Start_Time, row.End_Time
                )
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
                    if row.Category == 'Demo':
                        paper_type = 'demo'
                    elif row.Category == 'Industry':
                        paper_type = 'industry'
                    elif row.Category == 'SRW':
                        paper_type = 'srw'
                    elif row.Category == 'Findings':
                        paper_type = 'findings'
                    else:
                        paper_type = row.Category
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        anthology_entry = self.anthology_data[anthology_id]
                        abstract = anthology_entry.abstract
                        tldr = abstract[:TLDR_LENGTH] + "..."
                        anthology_publication_id = anthology_entry.anthology_id
                        if anthology_publication_id is None:
                            anthology_url = None
                            paper_pdf = None
                        else:
                            anthology_url, paper_pdf = self.get_anthology_urls(paper_type, row.Length, anthology_publication_id)
                    else:
                        abstract = ""
                        tldr = ""
                        anthology_url = None
                        paper_pdf = None

                    if paper_id in self.keywords:
                        kw = self.keywords[paper_id]
                        keywords = kw.keywords
                        languages = kw.languages
                    else:
                        keywords = []
                        languages = []

                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(
                            self.anthology_data, paper_id, row.Author
                        ),
                        track=group_track,
                        display_track=group_track,
                        paper_type=paper_type,
                        category=row.Category,
                        abstract=abstract,
                        keywords=keywords,
                        languages=languages,
                        tldr=tldr,
                        event_ids=[event.id],
                        similar_paper_ids=[],
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        anthology_url=anthology_url,
                        paper_pdf=paper_pdf,
                        slides_pdf=assets.slides_pdf,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_poster_papers(self):
        logging.info("Parsing poster papers")
        df = pd.read_csv(self.poster_tsv_path, sep="\t")
        # Industry papers are missing their track
        df.loc[df.Category == "Industry", "Track"] = "Industry"
        df = fix_col_names(df[df.PID.notnull()])
        group_type = "Poster"
        for (group_session, group_track), group in df.groupby(["Session", "Track"]):
            group = group.sort_values("Presentation Order")
            assert len(set(group.Location.values)) == 1
            room = group.iloc[0].Location
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            start_dt, end_dt = self._parse_start_end_dt(
                group.iloc[0].Date,
                group.iloc[0]["Start_Time"],
                group.iloc[0]["End_Time"],
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
                    display_name=group_session,
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
                start_dt, end_dt = self._parse_start_end_dt(
                    row.Date,
                    row.Start_Time,
                    row.End_Time,
                )
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
                    if row.Category == 'Demo':
                        paper_type = 'demo'
                    elif row.Category == 'Industry':
                        paper_type = 'industry'
                    elif row.Category == 'SRW':
                        paper_type = 'srw'
                    elif row.Category == 'Findings':
                        paper_type = 'findings'
                    else:
                        paper_type = row.Category
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        anthology_entry = self.anthology_data[anthology_id]
                        abstract = anthology_entry.abstract
                        tldr = abstract[:TLDR_LENGTH] + "..."
                        anthology_publication_id = anthology_entry.anthology_id
                        if anthology_publication_id is None:
                            anthology_url = None
                            paper_pdf = None
                        else:
                            anthology_url, paper_pdf = self.get_anthology_urls(paper_type, row.Length, anthology_publication_id)
                    else:
                        abstract = ""
                        tldr = ""
                        anthology_url = None
                        paper_pdf = None

                    if paper_id in self.keywords:
                        kw = self.keywords[paper_id]
                        keywords = kw.keywords
                        languages = kw.languages
                    else:
                        keywords = []
                        languages = []

                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(
                            self.anthology_data, paper_id, row.Author
                        ),
                        track=group_track,
                        display_track=group_track,
                        paper_type=paper_type,
                        category=row.Category,
                        abstract=abstract,
                        languages=languages,
                        keywords=keywords,
                        tldr=tldr,
                        event_ids=[event.id],
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        anthology_url=anthology_url,
                        paper_pdf=paper_pdf,
                        slides_pdf=assets.slides_pdf,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_oral_papers(self):
        logging.info("Parsing oral papers")
        df = pd.read_csv(self.oral_tsv_path, sep="\t")
        df = fix_col_names(df[df.PID.notnull()])
        # Industry papers are missing their track
        df.loc[df.Category == "Industry", "Track"] = "Industry"
        group_type = "Oral"
        for (group_session, group_track), group in df.groupby(["Session", "Track"]):
            group = group.sort_values("Presentation Order")
            room = group.iloc[0].Location
            event_name = get_session_event_name(group_session, group_track, group_type)
            event_id = name_to_id(event_name)
            start_dt, end_dt = self._parse_start_end_dt(
                group.iloc[0].Date,
                group.iloc[0]["Start_Time"],
                group.iloc[-1]["End_Time"],
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
                    display_name=group_session,
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
                    if row.Category == 'Demo':
                        paper_type = 'demo'
                    elif row.Category == 'Industry':
                        paper_type = 'industry'
                    elif row.Category == 'SRW':
                        paper_type = 'srw'
                    elif row.Category == 'Findings':
                        paper_type = 'findings'
                    else:
                        paper_type = row.Category
                    anthology_id = to_anthology_id(paper_id)
                    if anthology_id in self.anthology_data:
                        anthology_entry = self.anthology_data[anthology_id]
                        abstract = anthology_entry.abstract
                        tldr = abstract[:TLDR_LENGTH] + "..."
                        anthology_publication_id = anthology_entry.anthology_id
                        if anthology_publication_id is None:
                            anthology_url = None
                            paper_pdf = None
                        else:
                            anthology_url, paper_pdf = self.get_anthology_urls(paper_type, row.Length, anthology_publication_id)
                    else:
                        abstract = ""
                        tldr = ""
                        anthology_url = None
                        paper_pdf = None
                    
                    if paper_id in self.keywords:
                        kw = self.keywords[paper_id]
                        keywords = kw.keywords
                        languages = kw.languages
                    else:
                        keywords = []
                        languages = []

                    paper = Paper(
                        id=paper_id,
                        program=determine_program(row.Category),
                        title=row.Title,
                        authors=parse_authors(
                            self.anthology_data, paper_id, row.Author
                        ),
                        track=group_track,
                        display_track=group_track,
                        paper_type=paper_type,
                        category=row.Category,
                        abstract=abstract,
                        keywords=keywords,
                        languages=languages,
                        tldr=tldr,
                        event_ids=[event.id],
                        underline_id=assets.underline_id,
                        underline_url=assets.underline_url,
                        anthology_url=anthology_url,
                        paper_pdf=paper_pdf,
                        slides_pdf=assets.slides_pdf,
                        preview_image=assets.poster_preview_png,
                        poster_pdf=assets.poster_pdf,
                    )
                    self.papers[row.PID] = paper

    def _parse_underline_spreadsheet(self):
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
                # The sheet shows times in UTC, so we have to localize to UTC
                # Generally, UTC is the assumed format and then conversions made from it
                event_start = pytz.utc.localize(
                    datetime.datetime.strptime(event_start, "%B %d, %Y %H:%M")
                )
                event_end = sheet["H"][row].value
                event_end = pytz.utc.localize(
                    datetime.datetime.strptime(event_end, "%B %d, %Y %H:%M")
                )
                # We extract the date from the start date instead of the spreadsheet
                event_date = event_start.date()
                event = {
                    "name": event_name,
                    "desc": event_desc,
                    "date": event_date.isoformat(),
                    "start": event_start.isoformat(),
                    "end": event_end.isoformat(),
                    "underline_id": str(sheet["A"][row].value),
                }
                spreadsheet_info[track_name]["events"][event_id].append(event)
                row += 1
        except IndexError:
            pass
        self.spreadsheet_info = spreadsheet_info

    def _parse_extras_from_spreadsheet(self, socials_json):
        # Parse sessions not in the booklet
        self._parse_event_without_papers(
            self.spreadsheet_info,
            "Plenary Sessions",
            "Plenary Sessions",
        )
        self._parse_event_without_papers(
            self.spreadsheet_info,
            "Findings",
            "Workshops",
        )
        self._parse_multi_event_single_paper(
            self.spreadsheet_info,
            "Coffee Break",
            "Breaks",
        )
        # We no longer parse these events here.
        # self._parse_event_without_papers(self.spreadsheet_info, "Social", "Socials")
        # self._parse_multi_event_single_paper(
        #     self.spreadsheet_info,
        #     "Diversity and Inclusion",
        #     "Socials",
        # )
        # self._parse_multi_event_single_paper(
        #     self.spreadsheet_info,
        #     "Birds of a Feather",
        #     "Socials",
        # )

        # We parse those events in here instead
        self._parse_socials(socials_json)


    def _parse_socials(self, socials_json):
        new_sessions = []
        with open(socials_json, 'r') as fp:
            all_socials = json.load(fp)
        for social in all_socials:
            id = social['id']
            name = social['name']
            display_name = social['display_name']
            start_time = social['start_time']
            end_time = social['end_time']
            rc_link = social['link']
            room = social['room']

            event = Event(id=id,
                          session="event_session",
                          track=name,
                          start_time=start_time,
                          end_time=end_time,
                          chairs=[],
                          paper_ids=[],
                          link=rc_link,
                          room=room,
                          type="Socials")
            session = Session(id=id,
                              name=display_name,
                              display_name=display_name,
                              start_time=start_time,
                              end_time=end_time,
                              type="Socials",
                              events={'id': event})
            new_sessions.append((name, session))
        for (name, session) in new_sessions:
            self.sessions[name] = session


    def _parse_event_without_papers(
        self, spreadsheet_info, event_key, event_type, event_name=None
    ):
        for session_key in spreadsheet_info[event_key]["events"]:
            # Single session, single event, single dummy paper
            # We first create the session and store a variable to reference it.
            # Because this Session has a single event, we don't iterate here.
            event_data = spreadsheet_info[event_key]["events"][session_key][0]
            if event_data["underline_id"] in UNDERLINE_EVENTS_TO_SKIP:
                continue
            group_session = event_data["name"]
            self.sessions[group_session] = Session(
                id=name_to_id(group_session),
                name=group_session,
                display_name=group_session,
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
            if (
                group_session[0].casefold() == "w"
                and len(group_session.split(":")[0]) < 4
            ):
                # Workshop
                workshop_number = group_session.split(":")[0][1:].strip()
                event_id = name_to_id(f"workshop-{workshop_number}")
            else:
                event_id = name_to_id(group_session)
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

    def _parse_multi_event_single_paper(
        self,
        spreadsheet_info,
        event_key,
        event_type,
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
                display_name=group_session,
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
                # Hack to fix a single issue in the templates that generates two
                # events with the same ID
                if event_id == "birds-of-a-feather-6_-ethics-discussion-(socials)":
                    event_id = "birds-of-a-feather-9"
                else:
                    event_id = name_to_id(group_session)
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


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime,)):
            return obj.isoformat()


def main(
    oral_tsv: str = "private_data-acl2023/oral-papers.tsv",
    poster_tsv: str = "private_data-acl2023/poster-demo-papers.tsv",
    virtual_tsv: str = "private_data-acl2023/virtual-papers.tsv",
    spotlight_tsv: str = "private_data-acl2023/spotlight-papers.tsv",
    extras_xlsx: str = "private_data-acl2023/acl-2023-events-export-2023-07-09 (1).xlsx",
    acl_main_long_proceedings_yaml: str = "private_data-acl2023/main/long.yml",
    acl_main_short_proceedings_yaml: str = "private_data-acl2023/main/short.yml",
    acl_main_findings_proceedings_yaml: str = "private_data-acl2023/main/findings.yml",
    acl_demo_proceedings_yaml: str = "private_data-acl2023/demo/papers.yml",
    acl_industry_proceedings_yaml: str = "private_data-acl2023/industry/papers.yml",
    acl_srw_proceedings_yaml: str = "private_data-acl2023/SRW/papers.yml",
    workshop_papers_yml: str = "data/acl_2023/data/workshop_papers.yaml",
    workshops_yaml: str = "data/acl_2023/data/workshops.yaml",
    booklet_json: str = "data/acl_2023/data/booklet_data.json",
    socials_json: str = "data/acl_2023/data/socials_data.json",
    keywords_csv: str = "data/acl_2023/data/keywords.csv",
    acl_anthology_prefix: str = "https://aclanthology.org/",
    out_dir: str = "data/acl_2023/data/",
):
    parser = Acl2023Parser(
        oral_tsv_path=Path(oral_tsv),
        poster_tsv_path=Path(poster_tsv),
        virtual_tsv_path=Path(virtual_tsv),
        spotlight_tsv_path=Path(spotlight_tsv),
        extras_xlsx_path=Path(extras_xlsx),
        acl_main_long_proceedings_yaml_path=(acl_main_long_proceedings_yaml),
        acl_main_short_proceedings_yaml_path=(acl_main_short_proceedings_yaml),
        acl_main_findings_proceedings_yaml_path=(acl_main_findings_proceedings_yaml),
        acl_demo_proceedings_yaml_path=Path(acl_demo_proceedings_yaml),
        acl_industry_proceedings_yaml_path=Path(acl_industry_proceedings_yaml),
        acl_srw_proceedings_yaml_path=Path(acl_srw_proceedings_yaml),
        workshop_papers_yaml_path=Path(workshop_papers_yml),
        workshops_yaml_path=Path(workshops_yaml),
        booklet_json_path=Path(booklet_json),
        socials_json_path=Path(socials_json),
        keywords_csv_path=Path(keywords_csv),
        acl_anthology_prefix=acl_anthology_prefix,
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
