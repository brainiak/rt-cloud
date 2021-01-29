#!/usr/bin/env bash

# get commandline args - process the -h help arg
args=("${@}")
for i in ${!args[@]}; do
  if [[ ${args[i]} = "-h" ]]; then
    echo "USAGE: $0 [-u <username>] [-p <password>]"
    exit 0
  fi
  #echo "$i = ${args[i]}"
done

if [ ! -d "certs" ]; then
  mkdir certs
fi

if [ ! -f "certs/passwd" ]; then
  touch certs/passwd
fi

# activate rtcloud conda env if needed
if [ -z $CONDA_DEFAULT_ENV ] || [ $CONDA_DEFAULT_ENV != "rtcloud" ]; then
  source ~/.bashrc
  conda activate rtcloud
fi

export PYTHONPATH=./rtCommon/:$PYTHONPATH
echo "python rtCommon/addLogin.py ${args[@]}"
python rtCommon/addLogin.py ${args[@]}
