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

from acl_miniconf.load_site_data import load_site_data
from acl_miniconf.site_data import PlenarySession
from acl_miniconf.data import Conference, SiteData, ByUid, Paper

conference: Conference = None
site_data: SiteData = None
by_uid: ByUid = None

# ------------- SERVER CODE -------------------->

app = Flask(__name__)
app.config.from_object(__name__)
freezer = Freezer(app)
markdown = Markdown(app)

app.jinja_env.filters["quote_plus"] = quote_plus

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


@app.route("/about.html")
def about():
    data = _data()
    data["FAQ"] = site_data.faq
    data["CodeOfConduct"] = site_data.code_of_conduct
    return render_template("about.html", **data)


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
    data["event_types"] = site_data.event_types
    return render_template("schedule.html", **data)


@app.route("/livestream.html")
def livestream():
    data = _data()
    return render_template("livestream.html", **data)


@app.route("/plenary_sessions.html")
def plenary_sessions():
    data = _data()
    data["plenary_sessions"] = site_data.plenary_sessions
    data["plenary_session_days"] = site_data.plenary_session_days
    return render_template("plenary_sessions.html", **data)


@app.route("/sessions.html")
def sessions():
    data = _data()
    data["session_days"] = site_data.session_days
    data["sessions"] = site_data.sessions_by_day

    data["papers"] = {k: v.dict() for k, v in by_uid.papers.items()}
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


@app.route("/sponsors.html")
def sponsors():
    data = _data()
    data["sponsors"] = site_data.sponsors_by_level
    data["sponsor_levels"] = site_data.sponsor_levels
    return render_template("sponsors.html", **data)


@app.route("/socials.html")
def socials():
    data = _data()
    data["socials"] = site_data.socials
    return render_template("socials.html", **data)


@app.route("/organizers.html")
def organizers():
    data = _data()

    data["committee"] = site_data.committee
    return render_template("organizers.html", **data)


# ITEM PAGES


@app.route("/paper_<uid>.html")
def paper(uid):
    data = _data()

    v: Paper = by_uid.papers[uid]
    data["id"] = uid
    data["openreview"] = v
    data["paper"] = v
    data['events'] = [conference.events[e_id] for e_id in v.event_ids]
    data["paper_recs"] = [
        by_uid.papers[i] for i in v.similar_paper_ids[1:]
    ]

    return render_template("paper.html", **data)


@app.route("/plenary_session_<uid>.html")
def plenary_session(uid):
    data = _data()
    data["plenary_session"] = by_uid.plenary_sessions[uid]
    return render_template("plenary_session.html", **data)


@app.route("/tutorial_<uid>.html")
def tutorial(uid):
    data = _data()
    data["tutorial"] = by_uid.tutorials[uid]
    return render_template("tutorial.html", **data)


@app.route("/workshop_<uid>.html")
def workshop(uid):
    data = _data()
    data["workshop"] = by_uid.workshops[uid]
    return render_template("workshop.html", **data)


@app.route("/sponsor_<uid>.html")
def sponsor(uid):
    data = _data()
    data["sponsor"] = by_uid.sponsors[uid]
    data["papers"] = by_uid.papers
    return render_template("sponsor.html", **data)


@app.route("/chat.html")
def chat():
    data = _data()
    return render_template("chat.html", **data)


# FRONT END SERVING


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
    if program_name == "workshop":
        papers_for_track = None
        for wsh in site_data.workshops:
            if wsh.title == track_name:
                papers_for_track = wsh.papers
                break
    else:
        papers_for_track = [
            paper
            for paper in site_data.papers
            if paper.track == track_name
            and paper.program == program_name
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
    paper: Paper
    for paper in site_data.papers:
        yield "paper", {"uid": paper.id}

    for program in site_data.programs:
        yield "papers_program", {"program": program}
        for track in site_data.tracks:
            yield "track_json", {"track_name": track, "program_name": program}

    yield "papers_program", {"program": "workshop"}
    for wsh in site_data.workshops:
        yield "track_json", {"track_name": wsh.title, "program_name": "workshop"}

    plenary_session: PlenarySession
    for _, plenary_sessions_on_date in site_data.plenary_sessions.items():
        for plenary_session in plenary_sessions_on_date:
            yield "plenary_session", {"uid": plenary_session.id}

    for tutorial in site_data.tutorials:
        yield "tutorial", {"uid": tutorial.id}

    for workshop in site_data.workshops:
        yield "workshop", {"uid": workshop.id}

    for sponsor in site_data.sponsors:
        if "landingpage" in sponsor:
            continue
        yield "sponsor", {"uid": str(sponsor["UID"])}

    for key in site_data:
        yield "serve", {"path": key}


@hydra.main(version_base=None, config_path="configs", config_name="site")
def hydra_main(cfg: DictConfig):
    auto_data_dir = Path(cfg.auto_data_dir)
    data_dir = Path(cfg.data_dir)
    # TODO: Don't load pickle, load json, but need to figure out how to parse datetimes back into str
    global conference
    with open(auto_data_dir / 'conference.pkl', 'rb') as f:
        conference = pickle.load(f)
    if not data_dir.exists():
        raise AssertionError(
            f"Data directory {cfg.data_dir} not found in `data`. Please specify the correct data directory in config."
        )
    global site_data
    global by_uid
    site_data = SiteData.from_conference(conference, data_dir)
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
