#!/usr/bin/env bash

apt update
apt install -y python3-pip
apt install -y python3-venv

python -m pip install --upgrade pip poetry
poetry install
make freeze