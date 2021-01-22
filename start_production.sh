#!/bin/bash

branch=master
remote_branch="origin/${branch}"
python=python

while true
do
  # Note: this is the 100% correct way of safely updating a repository
  git reset --hard
  git fetch --all
  git checkout "${branch}"
  git reset --hard "${remote_branch}"
  git pull
  "${python}" -m pip install -r "`dirname $0`/requirements/base.txt"
  "${python}" "`dirname $0`/main.py"

  sleep 5
done
