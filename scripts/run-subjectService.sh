#!/usr/bin/env bash

## Any changes made to this file should ALSO be made to analysis_listener.sh!

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

# activate conda python env if needed
if [ -z $CONDA_DEFAULT_ENV ] || [ $CONDA_DEFAULT_ENV != "rtcloud" ]; then
  source ~/.bashrc
  CONDA_BASE=$(conda info --base)
  source $CONDA_BASE/etc/profile.d/conda.sh
  conda activate rtcloud
fi

export PYTHONPATH=./rtCommon/:$PYTHONPATH
echo "python rtCommon/subjectService.py ${args[@]}"
python rtCommon/subjectService.py ${args[@]}
