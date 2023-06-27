#!/usr/bin/env bash

apt update
apt install python3-pip

pip install pipx
pipx install poetry
poetry install
make freeze