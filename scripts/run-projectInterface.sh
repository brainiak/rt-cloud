#!/usr/bin/env bash

# get commandline params
while test $# -gt 0
do
  case "$1" in
    -h)
      echo "$0 -p <projectName> [-d <projectDir>] [-c <toml_file>] [-m <main_script.py>] [-ip <local_ip_or_hostname>] [--localfiles] [--test]"
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

R_PARAM=''
if [ -z $USELOCALFILES ]; then
  # USELOCALFILES not set, use remote files
  # TODO - have separate flags for dataRemote and subjectRemote
  R_PARAM='-x -s'
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
echo python rtCommon/projectServer.py -p $PROJECT $CFG_PARAM $MAIN_SCRIPT_PARAM $R_PARAM  $TEST_PARAM
python rtCommon/projectServer.py -p $PROJECT $CFG_PARAM $MAIN_SCRIPT_PARAM $R_PARAM  $TEST_PARAM
