#!/usr/bin/env bash

# Default Parameters
SERVER='localhost:8888'

# get commandline params
while test $# -gt 0
do
  case "$1" in
    -h)
      echo "$0 [-s <server:port>] [-u username] [-p password] [--test]"
      exit 0
      ;;
    -s) SERVER=$2
      ;;
    -u) USERNAME=$2
      ;;
    -p) PASSWORD=$2
      ;;
    --test) TEST='--test'
      ;;
  esac
  shift
done


# check if experiment file is supplied with -e filename
USER_PARAM=''
if [ ! -z $USERNAME ]; then
  USER_PARAM="-u $USERNAME"
fi

PASSWD_PARAM=''
if [ ! -z $PASSWORD ]; then
  PASSWD_PARAM="-p $PASSWORD"
fi


# activate conda python env
source ~/.bashrc
conda deactivate
conda activate rtcloud

export PYTHONPATH=./rtCommon/:$PYTHONPATH
python rtCommon/subjectService.py $USER_PARAM $PASSWD_PARAM -s $SERVER $TEST
