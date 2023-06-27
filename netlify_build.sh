#!/usr/bin/env bash

apt update

curl -sSL https://install.python-poetry.org | python3 -
poetry install
make freeze