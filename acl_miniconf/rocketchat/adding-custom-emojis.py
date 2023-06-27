import os
from pathlib import Path
import json
import requests

########################################################
#### Script for adding custom emojis for Rocket chat ###
########################################################

# define which API version to use


def main():
    api_auth_token = os.environ.get("RC_AUTH_TOKEN")
    user_id = os.environ.get("RC_USER_ID")
    server = os.environ.get("RC_SERVER")


if __name__ == "__main__":
    main()
