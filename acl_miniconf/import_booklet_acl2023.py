#!/usr/bin/python3
import datetime
import json
from typing import Dict, List, Tuple
import datetime

from pydantic import BaseModel
import yaml
from acl_miniconf.data import (
    TUTORIALS,
    WORKSHOPS,
    AnthologyAuthor,
    Plenary,
    Session,
    Workshop,
    Tutorial,
    PLENARIES,
    CONFERENCE_TZ,
)

WS_ID_TO_SHORT = {
    "workshop_1": "SemEval",
    "workshop_2": "DialDoc",
    "workshop_3": "CODI",
    "workshop_4": "IWSLT",
    "workshop_5": "RepL4NLP",
    "workshop_6": "SustaiNLP",
    "workshop_7": "BEA",
    "workshop_8": "NLRSE",
    "workshop_9": "WOAH",
    "workshop_10": "DialDoc",
    "workshop_11": "MATCHING",
    "workshop_12": "LAW",
    "workshop_13": "BioNLP-ST",
    "workshop_14": "NLP4ConvAI",
    "workshop_15": "TrustNLP",
    "workshop_16": "WASSA",
    "workshop_17": "Clinical-NLP",
    "workshop_18": "SICon",
    "workshop_19": "CAWL",
    "workshop_20": "AmericasNLP",
    "workshop_21": "Narrative-Understanding",
    "workshop_22": "SIGMORPHON",
}


class Booklet(BaseModel):
    plenaries: Dict[str, Plenary]
    plenary_sessions: Dict[str, Session]
    tutorials: Dict[str, Tutorial]
    tutorial_sessions: Dict[str, Session]
    workshops: Dict[str, Workshop]
    workshop_sessions: Dict[str, Session]

    @classmethod
    def from_booklet_data(cls, booklet_json_path: str, workshop_yaml_path: str):
        with open(booklet_json_path, "r") as fp:
            booklet_data = json.load(fp)
        plenary_sessions, plenaries = generate_plenaries(booklet_data["plenaries"])
        days = list(plenary_sessions.keys())
        days.sort()  # Hack fix
        plenary_session_days = [(idx, day, True) for idx, day in enumerate(days)]
        tutorial_sessions, tutorials = generate_tutorials(booklet_data["tutorials"])
        workshop_sessions, workshops = generate_workshops(
            workshop_yaml_path, booklet_data["workshops"]
        )
        return cls(
            plenaries=plenaries,
            plenary_sessions=plenary_sessions,
            tutorials=tutorials,
            tutorial_sessions=tutorial_sessions,
            workshops=workshops,
            workshop_sessions=workshop_sessions,
        )


def parse_conference_time(time_str: str):
    return CONFERENCE_TZ.localize(datetime.datetime.fromisoformat(time_str))


def generate_plenaries(
    plenaries_list: List[Dict],
) -> Tuple[Dict[str, Session], Dict[str, Plenary]]:
    plenaries = {}
    sessions = {}
    for plenary_dict in plenaries_list:
        # This is fine since the booklet is in Toronto time
        start_time = parse_conference_time(plenary_dict["start_time"])
        end_time = parse_conference_time(plenary_dict["end_time"])

        plenary_id = plenary_dict["id"]
        session_name = "Plenary: " + plenary_dict["title"]
        # Creating a session per plenary simplifies this
        event = Plenary(
            id=plenary_id,
            title="Plenary: " + plenary_dict["title"],
            image_url=plenary_dict["image"],
            presenter=plenary_dict["speaker_name"],
            institution=plenary_dict["institution"],
            abstract=plenary_dict["desc"],
            bio=plenary_dict["bio"],
            type=PLENARIES,
            room=plenary_dict["location"],
            session=plenary_id,
        )
        session = Session(
            id=plenary_id,
            name="Plenary: " + plenary_dict["title"],
            display_name=session_name,
            start_time=start_time,
            end_time=end_time,
            type=PLENARIES,
            plenary_events={plenary_id: event},
        )

        sessions[plenary_id] = session
        plenaries[plenary_id] = event
    return sessions, plenaries


def generate_tutorials(
    tutorial_list: List[Dict],
) -> Tuple[Dict[str, Session], Dict[str, Tutorial]]:
    sessions = {}
    tutorials = {}
    for tutorial_dict in tutorial_list:
        # Put the Tutorial event together
        tutorial_id = tutorial_dict["id"]
        start_time = parse_conference_time(tutorial_dict["start_time"])
        end_time = parse_conference_time(tutorial_dict["end_time"])
        tutorial = Tutorial(
            id=tutorial_id,
            title=tutorial_dict["title"],
            session=tutorial_id,
            organizers=tutorial_dict["hosts"],
            description=tutorial_dict["desc"],
            rocketchat_channel=tutorial_dict["rocketchat"],
            room=tutorial_dict["location"],
            start_time=start_time,
            end_time=end_time,
        )
        session = Session(
            id=tutorial_id,
            name=tutorial_dict["title"],
            display_name=tutorial_dict["title"],
            start_time=start_time,
            end_time=start_time,
            type=TUTORIALS,
            tutorial_events={tutorial_id: tutorial},
        )
        sessions[tutorial_id] = session
        tutorials[tutorial_id] = tutorial
    return sessions, tutorials


def generate_workshops(
    workshop_yaml_path: str,
    workshop_list: List[Dict],
) -> Tuple[Dict[str, Session], Dict[str, Workshop]]:
    with open(workshop_yaml_path) as f:
        workshops_anthology_info = yaml.safe_load(f)

    workshops_info_dict = {}
    for w in workshops_anthology_info:
        workshops_info_dict[w["short_name"]] = w["anthology_venue_id"]

    sessions = {}
    workshops = {}
    for workshop_dict in workshop_list:
        booklet_id = workshop_dict["id"]
        workshop_id = WS_ID_TO_SHORT[booklet_id]
        start_time = parse_conference_time(workshop_dict["start_time"])
        end_time = parse_conference_time(
            workshop_dict["start_time"]
        ) + datetime.timedelta(hours=8)
        workshop = Workshop(
            id=workshop_id,
            title=workshop_dict["title"],
            committee=[
                AnthologyAuthor(full_name=a.strip())
                for a in workshop_dict["chair"].split(",")
            ],
            workshop_site_url=workshop_dict["url"],
            description=workshop_dict["desc"],
            room=workshop_dict["location"],
            anthology_venue_id=workshops_info_dict[workshop_id],
            booklet_id=booklet_id,
            short_name=workshop_id,
            session=workshop_id,
        )
        session = Session(
            id=workshop_id,
            name=workshop_dict["title"],
            display_name=workshop_dict["title"],
            start_time=start_time,
            end_time=end_time,
            type=WORKSHOPS,
            workshop_events={workshop_id: workshop},
        )
        sessions[workshop_id] = session
        workshops[workshop_id] = workshop

    return sessions, workshops
