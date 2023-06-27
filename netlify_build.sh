#!/usr/bin/env bash

sudo apt update
sudo apt install -y python3-pip
sudo apt install -y python3-venv

pip install pipx
pipx install poetry
poetry install
make freeze