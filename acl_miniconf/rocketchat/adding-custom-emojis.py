import os
from pathlib import Path
import json
import requests

########################################################
#### Script for adding custom emojis for Rocket chat ###
########################################################

# define which API version to use
API_path = "/api/v1/"
CUSTOM_EMOJI_DIR = Path("rocketchat-custom-emojis/")


def main():
    api_auth_token = os.environ.get('RC_AUTH_TOKEN')
    user_id = os.environ.get("RC_USER_ID")
    server = os.environ.get("RC_SERVER")
    headers = {
        "X-Auth-Token": api_auth_token,
        "X-User-Id": user_id,
    }
    if api_auth_token is None or user_id is None or server is None:
        raise ValueError("RC Environment variables not set correctly")
    # get all emoji images - only include JPG, PNG, and GIF files
    emoji_files = [
        x
        for x in os.listdir(CUSTOM_EMOJI_DIR)
        if x.endswith(".png") or x.endswith(".jpg") or x.endswith(".gif")
    ]

    for emoji_f in emoji_files:
        emoji_name, emoji_aliases = emoji_f.split(".")[0].split("_")

        files = {
            "emoji": (emoji_f, open(CUSTOM_EMOJI_DIR + emoji_f, "rb")),
            "name": (None, emoji_name),
            "aliases": (None, emoji_aliases),
        }
        try:
            response = requests.post(
                server + API_path + "emoji-custom.create",
                headers=headers,
                files=files,
            )
            response.raise_for_status()
            print(json.loads(response.content)["success"])
        except requests.exceptions.HTTPError as err:
            print("Encountered error: ", err)
            print("File: ", emoji_f)


if __name__ == '__main__':
    main()