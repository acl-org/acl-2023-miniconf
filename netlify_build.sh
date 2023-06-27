#!/usr/bin/env bash

apt update
apt install -y python3.9-pip python3.9-venv

python3.9 -m pip install --upgrade pip poetry
poetry install
make freeze