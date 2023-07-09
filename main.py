# pylint: disable=global-statement,redefined-outer-name
import os
import pickle
from typing import Any, Dict, Optional
from urllib.parse import quote_plus
from pathlib import Path

import hydra
from omegaconf import DictConfig

from flask import Flask, jsonify, redirect, render_template, send_from_directory
from flask_frozen import Freezer
from flaskext.markdown import Markdown

from acl_miniconf.load_site_data import load_site_data, reformat_plenary_data
from acl_miniconf.data import WORKSHOP, Conference, SiteData, ByUid, Paper

conference: Conference = None
site_data: SiteData = None
by_uid: ByUid = None

# ------------- SERVER CODE -------------------->

app = Flask(__name__)
app.config.from_object(__name__)
freezer = Freezer(app)
markdown = Markdown(app)


def take_one(dictionary: Dict):
    return next(iter(dictionary.values()))


app.jinja_env.filters["quote_plus"] = quote_plus
app.jinja_env.filters["take_one"] = take_one

# MAIN PAGES


def _data():
    data = {"config": site_data.config}
    return data


@app.route("/")
def index():
    return redirect("/index.html")


# TOP LEVEL PAGES


@app.route("/index.html")
def home():
    data = _data()
    data["ack_text"] = site_data.pages["acknowledgement.md"]
    return render_template("index.html", **data)


@app.route("/papers.html")
def papers():
    data = _data()
    # The data will be loaded from `papers.json`.
    # See the `papers_json()` method and `static/js/papers.js`.
    data["tracks"] = site_data.main_program_tracks
    data["workshop_names"] = [wsh.title for wsh in site_data.workshops]
    return render_template("papers.html", **data)


@app.route("/papers_vis.html")
def papers_vis():
    data = _data()
    # The data will be loaded from `papers.json`.
    # See the `papers_json()` method and `static/js/papers.js`.
    data["tracks"] = site_data.main_program_tracks + ["System Demonstrations"]
    return render_template("papers_vis.html", **data)


@app.route("/papers_keyword_vis.html")
def papers_keyword_vis():
    data = _data()
    # The data will be loaded from `papers.json`.
    # See the `papers_json()` method and `static/js/papers.js`.
    data["tracks"] = site_data.tracks
    return render_template("papers_keyword_vis.html", **data)


@app.route("/schedule.html")
def schedule():
    data = _data()
    data["calendar"] = [e.dict() for e in site_data.calendar]
    data["event_types"] = site_data.session_types
    return render_template("schedule.html", **data)


@app.route("/livestream.html")
def livestream():
    data = _data()
    return render_template("livestream.html", **data)


@app.route("/plenary_sessions.html")
def plenary_sessions():
    data = _data()
    session_data, session_day_data = reformat_plenary_data(site_data.plenaries)
    data["plenary_sessions"] = session_data
    data["plenary_session_days"] = session_day_data
    return render_template("plenary_sessions.html", **data)


@app.route("/sessions.html")
def sessions():
    data = _data()
    data["session_days"] = site_data.session_days
    data["sessions"] = site_data.sessions_by_day

    event_types = set()
    for e in conference.events.values():
        event_types.add(e.type)
    event_types = sorted(event_types)
    data["event_types"] = event_types

    data["papers"] = {k: v.dict() for k, v in by_uid.papers.items()}
    # The sessions page is for paper sessions, other sessions are shown in schedule
    data["excluded_session_types"] = ["Breaks", "Plenary Sessions", "Socials"]
    return render_template("sessions.html", **data)


@app.route("/tutorials.html")
def tutorials():
    data = _data()
    data["tutorials"] = site_data.tutorials
    return render_template("tutorials.html", **data)


@app.route("/workshops.html")
def workshops():
    data = _data()
    data["workshops"] = site_data.workshops
    return render_template("workshops.html", **data)


@app.route("/socials.html")
def socials():
    data = _data()
    data["socials"] = site_data.socials
    return render_template("socials.html", **data)


# ITEM PAGES
@app.route("/paper_<uid>.html")
def paper(uid):
    data = _data()

    v: Paper = by_uid.papers[uid]
    data["id"] = uid
    data["openreview"] = v
    data["paper"] = v
    data["events"] = [
        conference.events[e_id] for e_id in v.event_ids if e_id in conference.events
    ]
    data["workshop_events"] = [
        conference.workshops[e_id]
        for e_id in v.event_ids
        if e_id in conference.workshops
    ]
    data["paper_recs"] = [by_uid.papers[i] for i in v.similar_paper_ids[1:]]
    # TODO: Fix
    data["zone"] = site_data.local_timezone

    return render_template("paper.html", **data)


@app.route("/plenary_session_<uid>.html")
def plenary_session(uid):
    data = _data()
    data["plenary_session"] = by_uid.plenaries[uid]
    return render_template("plenary_session.html", **data)


@app.route("/tutorial_<uid>.html")
def tutorial(uid):
    data = _data()
    data["tutorial"] = by_uid.tutorials[uid]
    return render_template("tutorial.html", **data)


@app.route("/workshop_<uid>.html")
def workshop(uid):
    data = _data()
    workshop = by_uid.workshops[uid]
    data["workshop"] = workshop
    papers = []
    for p in site_data.workshop_papers:
        if workshop.short_name in p.event_ids:
            papers.append(p)
    data['papers'] = papers
    data['rocketchat_channel'] = f'workshop-{workshop.short_name}'
    return render_template("workshop.html", **data)


@app.route("/chat.html")
def chat():
    data = _data()
    return render_template("chat.html", **data)

@app.route("/map.html")
def venue_map():
    data = _data()
    return render_template("map.html", **data)

# FRONT END SERVING
@app.route("/schedule.json")
def schedule_json():
    return jsonify([e.dict() for e in site_data.calendar])


@app.route("/papers.json")
def papers_json():
    return jsonify([p.dict() for p in site_data.papers])


@app.route("/papers_<program>.json")
def papers_program(program: str):
    if program == "workshop":
        papers_for_program = []
        for wsh in site_data.workshops:
            papers_for_program.extend(wsh.papers)
    else:
        papers_for_program = [
            paper.dict() for paper in site_data.papers if paper.program == program
        ]
    return jsonify(papers_for_program)


@app.route("/track_<program_name>_<track_name>.json")
def track_json(program_name, track_name):
    if program_name == WORKSHOP:
        papers_for_track = None
        for wsh in site_data.workshops:
            if wsh.title == track_name:
                papers_for_track = wsh.papers
                break
    else:
        papers_for_track = [
            paper.dict()
            for paper in site_data.papers
            if paper.track == track_name and paper.program == program_name
        ]
    return jsonify(papers_for_track)


@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory("static", path)


@app.route("/serve_<path>.json")
def serve(path):
    return jsonify(site_data[path])


# --------------- DRIVER CODE -------------------------->
# Code to turn it all static


@freezer.register_generator
def generator():
    for paper in site_data.papers:
        yield "paper", {"uid": paper.id}

    for program in site_data.programs:
        yield "papers_program", {"program": program}
        for track in site_data.track_ids:
            yield "track_json", {"track_name": track, "program_name": program}

    yield "papers_program", {"program": WORKSHOP}
    for wsh in site_data.workshops:
        yield "track_json", {"track_name": wsh.title, "program_name": WORKSHOP}

    for plenary_key, _ in site_data.plenaries.items():
        yield "plenary_session", {"uid": plenary_key}

    for tutorial in site_data.tutorials.values():
        yield "tutorial", {"uid": tutorial.id}

    for workshop in site_data.workshops.values():
        yield "workshop", {"uid": workshop.id}

    # for key in site_data:
    #    yield "serve", {"path": key}


@hydra.main(version_base=None, config_path="configs", config_name="site")
def hydra_main(cfg: DictConfig):
    data_dir = Path(cfg.data_dir)
    # TODO: Don't load pickle, load json, but need to figure out how to parse datetimes back into str
    global conference
    conference = Conference.parse_file(data_dir / "data" / "conference.json")
    if not data_dir.exists():
        raise AssertionError(
            f"Data directory {cfg.data_dir} not found in `data`. Please specify the correct data directory in config."
        )
    global site_data
    global by_uid
    site_data = SiteData.from_conference(
        conference,
        data_dir,
    )
    site_data.local_timezone = cfg.time_zone
    by_uid = ByUid()
    extra_files = load_site_data(conference, site_data, by_uid)

    if cfg.build:
        freezer.freeze()
    else:
        debug_val = cfg.debug
        if os.getenv("FLASK_DEBUG") == "True":
            debug_val = True

        app.run(host=cfg.host, port=cfg.port, debug=debug_val, extra_files=extra_files)


if __name__ == "__main__":
    hydra_main()
