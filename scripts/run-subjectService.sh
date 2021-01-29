#!/usr/bin/env bash

### Default Parameters Set within subjectService ##
# SERVER='localhost:8888'
# Retry Connection Interval: 5 sec

# get commandline args - process the -h help arg
args=("${@}")
for i in ${!args[@]}; do
  if [[ ${args[i]} = "-h" ]]; then
    echo "USAGE: $0 [-s <server>] [-u <username>] [-p <password>]"
    echo -e "\t[-i <retry-connection-interval>] [--test]"
    exit 0
  fi
  #echo "$i = ${args[i]}"
done

# activate conda python env
source ~/.bashrc
conda deactivate
conda activate rtcloud

export PYTHONPATH=./rtCommon/:$PYTHONPATH
echo "python rtCommon/subjectService.py ${args[@]}"
python rtCommon/subjectService.py ${args[@]}
