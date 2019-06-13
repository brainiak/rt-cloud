#!/usr/bin/env bash

if [ ! -d "certs" ]; then
  mkdir certs
fi

if [ ! -f "certs/passwd" ]; then
  touch certs/passwd
fi

python rtCommon/addLogin.py
