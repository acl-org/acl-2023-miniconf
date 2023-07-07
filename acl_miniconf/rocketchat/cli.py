from pathlib import Path
import os
from typing import List
import pickle
import json

import requests
import hydra
from omegaconf import DictConfig
from requests import sessions
from rocketchat_API.rocketchat import RocketChat
import yaml
from acl_miniconf.data import Conference
from rich.progress import track


def paper_id_to_channel_name(paper_id: str):
    channel_name = f"paper-{paper_id}"
    channel_name = channel_name.replace(".", "-")
    return channel_name


API_path = "/api/v1/"
CUSTOM_EMOJI_DIR = Path("rocketchat-custom-emojis/")


class AclRcHelper:
    def __init__(
        self,
        *,
        program_json_path: str,
        booklet_json_path: str,
        workshops_yaml_path: str,
        user_id: str,
        auth_token: str,
        server: str,
        session: sessions.Session,
        dry_run: bool = False,
    ):
        self.conference: Conference = Conference.parse_file(program_json_path)
        with open(booklet_json_path) as f:
            self.booklet = json.load(f)

        with open(workshops_yaml_path) as f:
            self.workshops = yaml.safe_load(f)
        self.dry_run = dry_run
        self.auth_token = auth_token
        self.user_id = user_id
        self.server = server
        self.rocket = RocketChat(
            user_id=user_id,
            auth_token=auth_token,
            server_url=server,
            session=session,
        )

    def get_channel_names(self) -> List[str]:
        return [
            c["name"] for c in self.rocket.channels_list(count=0).json()["channels"]
        ]

    def create_channel(
        self, name: str, topic: str, description: str, create: bool = True
    ):
        if self.dry_run:
            print("Dry Run: Creating " + name + " topic " + topic)
        else:
            if create:
                created = self.rocket.channels_create(name).json()
                if not created["success"]:
                    raise ValueError(f"Bad response: name={name} response={created}")
                channel_id = created["channel"]["_id"]
            else:
                channel_id = self.rocket.channels_info(channel=name).json()["channel"][
                    "_id"
                ]
            self.rocket.channels_set_topic(channel_id, topic).json()
            self.rocket.channels_set_description(channel_id, description).json()

    def create_tutorial_channels(self):
        existing_channels = set(self.get_channel_names())
        skipped = 0
        created = 0
        for tutorial in track(self.booklet["tutorials"]):
            tutorial_id = tutorial["id"].replace("t", "")
            channel_name = f"tutorial-{tutorial_id}"
            author_string = ", ".join(tutorial["hosts"])
            title = tutorial["title"]
            topic = f"{title} - {author_string}"
            create = channel_name not in existing_channels
            self.create_channel(channel_name, topic, tutorial["desc"], create=create)
            created += 1

        print(
            f"Total tutorials: {len(self.conference.papers)}, Created: {created} Skipped: {skipped} Total: {created + skipped}"
        )

    def create_workshop_channels(self):
        existing_channels = set(self.get_channel_names())
        skipped = 0
        created = 0

        for ws in track(self.workshops):
            if ws["short_name"] == "inputs":
                workshop_id = ws["anthology_venue_id"]
            else:
                workshop_id = ws["short_name"]
            channel_name = f"workshop-{workshop_id}"
            title = ws["name"]
            topic = f"{title} - {workshop_id}"
            create = channel_name not in existing_channels
            self.create_channel(channel_name, topic, topic, create=create)
            created += 1

        print(
            f"Total workshops: {len(self.conference.papers)}, Created: {created} Skipped: {skipped} Total: {created + skipped}"
        )

    def create_paper_channels(self):
        existing_channels = set(self.get_channel_names())
        skipped = 0
        created = 0
        for paper in track(self.conference.papers.values()):
            if paper.is_paper:
                channel_name = paper_id_to_channel_name(paper.id)
                if channel_name in existing_channels:
                    skipped += 1
                else:
                    author_string = ", ".join(paper.authors)
                    topic = f"{paper.title} - {author_string}"
                    self.create_channel(channel_name, topic, paper.abstract)
                    created += 1

        print(
            f"Total papers: {len(self.conference.papers)}, Created: {created} Skipped: {skipped} Total: {created + skipped}"
        )

    def add_custom_emojis(self):
        headers = {
            "X-Auth-Token": self.auth_token,
            "X-User-Id": self.user_id,
        }
        # get all emoji images - only include JPG, PNG, and GIF files
        emoji_files = [
            x
            for x in os.listdir(CUSTOM_EMOJI_DIR)
            if x.endswith(".png") or x.endswith(".jpg") or x.endswith(".gif")
        ]

        for emoji_f in track(emoji_files):
            emoji_name, emoji_aliases = emoji_f.split(".")[0].split("_")

            files = {
                "emoji": (emoji_f, open(CUSTOM_EMOJI_DIR / emoji_f, "rb")),
                "name": (None, emoji_name),
                "aliases": (None, emoji_aliases),
            }
            try:
                response = requests.post(
                    self.server + API_path + "emoji-custom.create",
                    headers=headers,
                    files=files,
                )
                response.raise_for_status()
                print(json.loads(response.content)["success"])
            except requests.exceptions.HTTPError as err:
                print("Encountered error: ", err)
                print("File: ", emoji_f)


@hydra.main(
    version_base=None, config_path="../../configs/rocketchat", config_name="template"
)
def hydra_main(cfg: DictConfig):
    command = cfg.command

    if command == "create_paper_channels":
        with sessions.Session() as session:
            helper = AclRcHelper(
                user_id=cfg.user_id,
                auth_token=cfg.auth_token,
                server=cfg.server,
                session=session,
                program_json_path=Path(cfg.program_json_path),
                booklet_json_path=Path(cfg.booklet_json_path),
                workshops_yaml_path=Path(cfg.workshops_yaml_path),
                dry_run=cfg.dry_run,
            )
            helper.create_paper_channels()
    elif command == "create_tutorial_channels":
        with sessions.Session() as session:
            helper = AclRcHelper(
                user_id=cfg.user_id,
                auth_token=cfg.auth_token,
                server=cfg.server,
                session=session,
                program_json_path=Path(cfg.program_json_path),
                booklet_json_path=Path(cfg.booklet_json_path),
                workshops_yaml_path=Path(cfg.workshops_yaml_path),
                dry_run=cfg.dry_run,
            )
            helper.create_tutorial_channels()
    elif command == "create_workshop_channels":
        with sessions.Session() as session:
            helper = AclRcHelper(
                user_id=cfg.user_id,
                auth_token=cfg.auth_token,
                server=cfg.server,
                session=session,
                program_json_path=Path(cfg.program_json_path),
                booklet_json_path=Path(cfg.booklet_json_path),
                workshops_yaml_path=Path(cfg.workshops_yaml_path),
                dry_run=cfg.dry_run,
            )
            helper.create_workshop_channels()
    elif command == "add_emojis":
        with sessions.Session() as session:
            helper = AclRcHelper(
                user_id=cfg.user_id,
                auth_token=cfg.auth_token,
                server=cfg.server,
                session=session,
                program_json_path=Path(cfg.program_json_path),
                booklet_json_path=Path(cfg.booklet_json_path),
                workshops_yaml_path=Path(cfg.workshops_yaml_path),
                dry_run=cfg.dry_run,
            )
            helper.add_custom_emojis()


if __name__ == "__main__":
    hydra_main()
