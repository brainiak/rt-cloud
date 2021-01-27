#!/usr/bin/env bash

# get commandline params
while test $# -gt 0
do
  case "$1" in
    -h)
      echo "$0 -p <projectName> [-d <projectDir>] [-c <toml_file>] [-m <main_script.py>] [-ip <local_ip_or_hostname>] [--localfiles] [--localsubject] [--test]"
      exit 0
      ;;
    -c) CFG=$2
      ;;
    -ip) IP=$2
      ;;
    -p) PROJECT=$2
      ;;
    -d) PROJECT_DIR=$2
      ;;
    -m) MAIN_SCRIPT=$2
      ;;
    --localfiles) USELOCALFILES=1
      ;;
    --localsubject) USELOCALSUBJECT=1
      ;;
    --test) TEST_PARAM='-t'
      ;;
  esac
  shift
done

if [ -z $PROJECT ]; then
  # USELOCALFILES not set, use remote files
  echo 'must specify a project name with -p option'
  exit 0
fi

# check if experiment file is supplied with -e filename
CFG_PARAM=''
if [ ! -z $CFG ]; then
  CFG_PARAM="-c $CFG"
fi

MAIN_SCRIPT_PARAM=''
if [ ! -z $MAIN_SCRIPT ]; then
  MAIN_SCRIPT_PARAM="-m $MAIN_SCRIPT"
fi

DATA_REMOTE_PARAM=''
if [ -z $USELOCALFILES ]; then
  # USELOCALFILES not set, use remote files
  DATA_REMOTE_PARAM='-x'
fi

SUBJECT_REMOTE_PARAM=''
if [ -z $USELOCALSUBJECT ]; then
  # USELOCALSUBJECT not set, use subject setting
  SUBJECT_REMOTE_PARAM='-s'
fi

pushd web
npm run build
popd

if [ -z $IP ]; then
  echo "Warning: no ip address supplied, credentials won't be updated"
else
  bash scripts/make-sslcert.sh -ip $IP
fi

# activate rtcloud conda env if needed
if [ -z $CONDA_DEFAULT_ENV ] || [ $CONDA_DEFAULT_ENV != "rtcloud" ]; then
  source ~/.bashrc
  conda activate rtcloud
fi

export PYTHONPATH=./rtCommon/:$PYTHONPATH
python rtCommon/projectServer.py -p $PROJECT $CFG_PARAM $MAIN_SCRIPT_PARAM $DATA_REMOTE_PARAM $SUBJECT_REMOTE_PARAM $TEST_PARAM
