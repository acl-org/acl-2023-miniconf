#!/usr/bin/python3
import datetime
import json
from .site_data import Tutorial, SessionInfo, PlenarySession, Workshop


def generate_plenaries(plenaries_list):
    plenaries = {}
    for plenary_dict in plenaries_list:
        day = datetime.datetime.fromisoformat(plenary_dict["start_time"]).strftime("%A")
        if day not in plenaries:
            plenaries[day] = []
        plenaries[day].append(
            PlenarySession(
                id=plenary_dict["id"],
                title=plenary_dict["title"],
                image=plenary_dict["image"],
                day=day,
                sessions=[],
                presenter=plenary_dict["speaker_name"],
                institution=plenary_dict["institution"],
                abstract=plenary_dict["desc"],
                bio=plenary_dict["bio"],
                presentation_id=None,
                rocketchat_channel=None,
                videos=[],
            )
        )
    return plenaries


def generate_tutorials(tutorial_list):
    tutorials = []
    for tutorial_dict in tutorial_list:
        # Put the Tutorial event together
        blocks = [
            SessionInfo(
                session_name=tutorial_dict["start_time"],
                start_time=datetime.datetime.fromisoformat(tutorial_dict["start_time"]),
                end_time=datetime.datetime.fromisoformat(tutorial_dict["end_time"]),
                hosts=tutorial_dict["hosts"],
                link=None,
            )
        ]
        day = datetime.datetime.fromisoformat(tutorial_dict["start_time"]).strftime(
            "%A"
        )
        final_tutorial = Tutorial(
            id=tutorial_dict["id"],
            title=tutorial_dict["title"],
            organizers=", ".join(tutorial_dict["hosts"]),
            abstract=tutorial_dict["desc"],
            rocketchat_channel=tutorial_dict["rocketchat"],
            sessions=[],
            blocks=blocks,
            virtual_format_description=None,
            website=None,
            material=None,
            slides=None,
            prerecorded=None,
        )
        tutorials.append(final_tutorial)
    return tutorials


def generate_workshops(workshop_list):
    workshops = []
    for workshop_dict in workshop_list:
        blocks = [
            SessionInfo(
                session_name=datetime.datetime.fromisoformat(
                    workshop_dict["start_time"]
                ).strftime("%A"),
                start_time=datetime.datetime.fromisoformat(workshop_dict["start_time"]),
                end_time=datetime.datetime.fromisoformat(workshop_dict["start_time"])
                + datetime.timedelta(hours=8),
                hosts=workshop_dict["chair"],
                link=workshop_dict["url"],
            )
        ]
        final_workshop = Workshop(
            id=workshop_dict["id"],
            title=workshop_dict["title"],
            organizers=workshop_dict["chair"],
            abstract=workshop_dict["desc"],
            website=workshop_dict["url"],
            papers=[],
            livestream=None,
            schedule=[],
            prerecorded_talks=[],
            rocketchat_channel="",
            sessions=None,
            blocks=blocks,
            zoom_links=[],
        )
        workshops.append(final_workshop)
    return workshops
