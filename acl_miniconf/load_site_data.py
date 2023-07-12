import copy
import datetime
import re
from datetime import timedelta
from typing import Any, DefaultDict, Dict, List, Optional

import pytz

from acl_miniconf.data import (
    EVENT_TYPES,
    Conference,
    SiteData,
    ByUid,
    FrontendCalendarEvent,
)


def load_site_data(
    conference: Conference,
    site_data: SiteData,
    by_uid: ByUid,
) -> List[str]:
    """Loads all site data at once.

    Populates the `committee` and `by_uid` using files under `site_data_path`.

    NOTE: site_data[filename][field]
    """
    # schedule.html
    # generate_plenary_events(site_data)
    # generate_tutorial_events(site_data)
    # generate_workshop_events(site_data)
    site_data.overall_calendar: List[FrontendCalendarEvent] = []
    site_data.overall_calendar.extend(generate_paper_events(site_data))
    # site_data.overall_calendar.extend(generate_social_events(site_data))
    # generate_social_events(site_data)

    site_data.calendar = build_schedule(site_data.overall_calendar)
    site_data.session_types = list({event.type for event in site_data.overall_calendar})
    # paper_<uid>.html
    by_uid.papers = conference.papers
    by_uid.plenaries = conference.plenaries
    by_uid.tutorials = conference.tutorials
    by_uid.workshops = conference.workshops

    # workshops.html
    # workshops = build_workshops(
    #     raw_workshops=site_data["workshops"],
    #     raw_workshop_papers=site_data["workshop_papers"],
    # )
    # site_data["workshops"] = workshops
    # # workshop_<uid>.html
    # by_uid["workshops"] = {workshop.id: workshop for workshop in workshops}

    # # socials.html
    # social_events = build_socials(site_data["socials"])
    # site_data["socials"] = social_events

    # # serve_papers_projection.json
    # all_paper_ids_with_projection = {
    #     item["id"] for item in site_data["papers_projection"]
    # }
    # for paper_id in set(by_uid["papers"].keys()) - all_paper_ids_with_projection:
    #     paper = by_uid["papers"][paper_id]
    #     if paper.content.program == "main":
    #         print(f"WARNING: {paper_id} does not have a projection")


def extract_list_field(v, key):
    value = v.get(key, "")
    if isinstance(value, list):
        return value
    else:
        return value.split("|")


def generate_paper_events(site_data: SiteData) -> List[Dict[str, Any]]:
    """We add sessions from papers and compute the overall paper blocks for the weekly view."""
    # Add paper sessions to calendar
    overall_calendar = []
    for uid, session in site_data.sessions.items():
        start = session.start_time
        end = session.end_time
        tab_id = (
            session.start_time.astimezone(pytz.utc)
            .strftime("%B %d")
            .replace(" ", "")
            .lower()
        )
        if session.type == "Plenary Sessions":
            url = f"plenary_sessions.html#tab-{tab_id}"
        elif session.type == "Workshops":
            url = f"workshops.html#tab-{tab_id}"
        elif session.type == "Tutorials":
            url = f"tutorials.html#tab-{tab_id}"
        elif session.type == "Socials":
            url = f"socials.html#tab-{tab_id}"
        else:
            url = f"sessions.html#link-{tab_id}-{session.id}"

        event = FrontendCalendarEvent(
            title=session.name,
            start=session.start_time,
            end=session.end_time,
            location="",
            url=url,
            category="time",
            type=session.type,
            view="week",
        )
        overall_calendar.append(event)
        existing_events = set()
        for event in session.events.values():
            if (event.session, event.track, event.start_time) not in existing_events:
                if event.type == 'Socials':
                    url = "/socials.html"
                elif event.type == 'Plenary Sessions':
                    url = "/plenary_sessions.html"
                else:
                    url = f"/sessions.html#link-{tab_id}-{event.id}"
                frontend_event = FrontendCalendarEvent(
                    title=f"<b>{event.track}</b>",
                    start=start,
                    end=end,
                    location="",
                    #url=f"papers.html?session={session.id}&program=all",
                    url=url,
                    category="time",
                    type=session.type,
                    view="day",
                )
                # We don't want repeats of types, just collect all matching session/track
                # into one page
                existing_events.add((event.session, event.track, event.start_time))
                overall_calendar.append(frontend_event)

                assert start <= end, f"Session start after session end: {session.id} {event.id}\n{start} {end}\n{event.start_time} {event.end_time}"

        for event in session.tutorial_events.values():
            if (event.session, event.track, event.start_time) not in existing_events:
                frontend_event = FrontendCalendarEvent(
                    title=f"<b>{event.track}</b>",
                    start=start,
                    end=end,
                    location="",
                    # TODO: UID probably doesn't work here
                    url=f"tutorial_{event.id}.html",
                    category="time",
                    type=session.type,
                    view="day",
                )
                # We don't want repeats of types, just collect all matching session/track
                # into one page
                existing_events.add((event.session, event.track, event.start_time))
                overall_calendar.append(frontend_event)

                assert start <= end, f"Session start after session end: {session.id} {event.id}\n{start} {end}\n{event.start_time} {event.end_time}"

        for event in session.plenary_events.values():
            if (event.session, event.track, event.start_time) not in existing_events:
                frontend_event = FrontendCalendarEvent(
                    title=f"<b>{event.track}</b>",
                    start=start,
                    end=end,
                    location=event.room,
                    url=f"plenary_sessions.html",
                    category="time",
                    type=session.type,
                    view="day",
                )
                # We don't want repeats of types, just collect all matching session/track
                # into one page
                existing_events.add((event.session, event.track, event.start_time))
                overall_calendar.append(frontend_event)

                assert start <= end, f"Session start after session end: {session.id} {event.id}\n{start} {end}\n{event.start_time} {event.end_time}"

        for event in session.workshop_events.values():
            if (event.session, event.track, event.start_time) not in existing_events:
                frontend_event = FrontendCalendarEvent(
                    title=f"<b>{event.track}</b>",
                    start=start,
                    end=end,
                    location=event.room,
                    # TODO: UID probably doesn't work here
                    url=f"workshop_{event.short_name}.html",
                    category="time",
                    type=session.type,
                    view="day",
                )
                # We don't want repeats of types, just collect all matching session/track
                # into one page
                existing_events.add((event.session, event.track, event.start_time))
                overall_calendar.append(frontend_event)

                assert start <= end, f"Session start after session end: {session.id} {event.id}\n{start} {end}\n{event.start_time} {event.end_time}"

    # for uid, group in all_grouped.items():
    #     name = group[0].name
    #     start_time = group[0].start_time
    #     end_time = group[0].end_time
    #     assert all(s.start_time == start_time for s in group)
    #     assert all(s.end_time == end_time for s in group)

    #     event = FrontendCalendarEvent(
    #         title=name,
    #         start=start_time,
    #         end=end_time,
    #         location="",
    #         url=f"sessions.html#tab-{tab_id}",
    #         category="time",
    #         type="Paper Sessions",
    #         view="week",
    #     )
    #     overall_calendar.append(event)
    return overall_calendar


def generate_social_events(site_data: SiteData) -> List[Dict[str, Any]]:
    """We add social sessions and compute the overall paper social for the weekly view."""
    # Add paper sessions to calendar
    overall_calendar = []
    for uid, session in site_data.sessions.items():
        if session.type != "Socials":
            continue
        start = session.start_time
        end = session.end_time
        tab_id = (
            session.start_time.astimezone(pytz.utc)
            .strftime("%B %d")
            .replace(" ", "")
            .lower()
        )
        event = FrontendCalendarEvent(
            title=session.name,
            start=session.start_time,
            end=session.end_time,
            location="",
            url=f"socials.html",
            category="time",
            type=session.type,
            view="week",
        )
        overall_calendar.append(event)
        existing_events = set()
        for event in session.events.values():
            if (event.session, event.track, event.start_time) not in existing_events:
                frontend_event = FrontendCalendarEvent(
                    title=f"<b>{event.track}</b>",
                    start=start,
                    end=end,
                    location="",
                    # TODO: UID probably doesn't work here
                    url=f"socials.html",
                    category="time",
                    type=session.type,
                    view="day",
                )
                # We don't want repeats of types, just collect all matching session/track
                # into one page
                existing_events.add((event.session, event.track, event.start_time))
                overall_calendar.append(frontend_event)

                assert start < end, "Session start after session end"
    return overall_calendar


def build_schedule(
    overall_calendar: List[FrontendCalendarEvent],
) -> List[FrontendCalendarEvent]:
    events = [
        copy.deepcopy(event) for event in overall_calendar if event.type in EVENT_TYPES
    ]

    for event in events:
        event_type = event.type
        if event_type == "Plenary Sessions":
            event.classNames = ["calendar-event-plenary"]
        elif event_type == "Tutorials":
            event.classNames = ["calendar-event-tutorial"]
        elif event_type == "Workshops":
            event.classNames = ["calendar-event-workshops"]
        elif event_type == "Paper Sessions":
            event.classNames = ["calendar-event-paper-sessions"]
        elif event_type == "Socials":
            event.classNames = ["calendar-event-socials"]
        elif event_type == "Sponsors":
            event.classNames = ["calendar-event-sponsors"]
        else:
            event.classNames = ["calendar-event-other"]

        event.classNames.append("calendar-event")
    return events


def build_tutorial_schedule(
    overall_calendar: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    events = [
        copy.deepcopy(event)
        for event in overall_calendar
        if event["type"] in {"Tutorials"}
    ]

    for event in events:
        event["classNames"] = ["calendar-event-tutorial"]
        event["url"] = event["link"]
        event["classNames"].append("calendar-event")
    return events


def normalize_track_name(track_name: str) -> str:
    if track_name == "SRW":
        return "Student Research Workshop"
    elif track_name == "Demo":
        return "System Demonstrations"
    return track_name


def get_card_image_path_for_paper(paper_id: str, paper_images_path: str) -> str:
    return f"{paper_images_path}/{paper_id}.png"


def compute_schedule_blocks(
    events, leeway: Optional[timedelta] = None
) -> List[List[Dict[str, Any]]]:
    if leeway is None:
        leeway = timedelta()

    # Based on
    # https://stackoverflow.com/questions/54713564/how-to-find-gaps-given-a-number-of-start-and-end-datetime-objects
    if len(events) <= 1:
        return events

    # sort by start times
    events = sorted(events, key=lambda x: x["start_time"])

    # Start at the end of the first range
    now = events[0]["end_time"]

    blocks = []
    block: List[Dict[str, Any]] = []

    for pair in events:
        # if next start time is before current end time, keep going until we find a gap
        # if next start time is after current end time, found the first gap
        if pair["start_time"] - (now + leeway) > timedelta():
            blocks.append(block)
            block = [pair]
        else:
            block.append(pair)

        # need to advance "now" only if the next end time is past the current end time
        now = max(pair["end_time"], now)

    if len(block):
        blocks.append(block)

    return blocks


def reformat_plenary_data(plenaries):
    # Massages the data a bit to match what the template expects.
    # We would typically do this at an earlier stage, but by doing it here
    # we break less stuff. I do not recommend doing this in general.
    session_data = dict()
    session_day_data = []

    re_date = re.compile("(\w+), July (\d+).*")
    re_time = re.compile(".*Time: (\d+:\d+).(\d+:\d+).*")
    for plenary_key, plenary in plenaries.items():
        # Parse the date and time from the description
        result_date = re_date.search(plenary.abstract)
        date_string = "2023-07-{}".format(result_date.group(2))
        plenary_day = result_date.group(1)
        result_time = re_time.search(plenary.abstract)
        start_time_string = result_time.group(1)
        end_time_string = result_time.group(2)
        # We add 6 hours here because there are issues with timezones that
        # were missed before.
        start_time = datetime.datetime.strptime(
            "{} {}".format(date_string, start_time_string), "%Y-%m-%d %H:%M"
        )
        start_time = start_time + datetime.timedelta(hours=6)
        end_time = datetime.datetime.strptime(
            "{} {}".format(date_string, end_time_string), "%Y-%m-%d %H:%M"
        )
        end_time = end_time + datetime.timedelta(hours=6)
        # Load images if we have one
        if plenary_key == "memorial":
            plenary.image_url = "invited/drago.jpg"
            plenary.abstract = plenary.abstract.replace('[image]', '').strip()
        elif plenary_key == "two-paths-to-intelligence":
            plenary.image_url = "invited/invited1.jpg"
        elif plenary_key[:10] == "large-lang":
            plenary.image_url = "invited/invited2.jpg"
        elif plenary_key[:10] == "the-future":
            plenary.image_url = "invited/invited3.jpg"
        else:
            plenary.image_url = "acl2023/acl-logo.png"
        # Add the existing dates to a list of all possible dates
        if plenary_day not in session_data:
            session_data[plenary_day] = []
            session_day_data.append(plenary_day)
        plenary.start_time = start_time
        plenary.end_time = end_time
        session_data[plenary_day].append(plenary)

    # Sorting days like this only works in this very specific case.
    session_day_data.sort()
    session_day_data = [
        (f"july1{idx}", day, idx == 0) for idx, day in enumerate(session_day_data)
    ]
    return session_data, session_day_data
