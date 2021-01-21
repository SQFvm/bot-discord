#!/bin/bash

while true
do
  git pull
  python -m pip install -r "`dirname $0`/requirements/base.txt"
  python main.py

  sleep 5
done