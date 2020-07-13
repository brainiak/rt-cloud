#!/usr/bin/env bash

# Default Parameters
SERVER='localhost:8888'
ALLOWDIRS='/tmp,/data'
ALLOWFILES='.dcm,.mat,.txt'

# get commandline params
while test $# -gt 0
do
  case "$1" in
    -h)
      echo "$0 [-s <server:port>] [-d <allowed_dirs>] [-f <allowed_file_extensions] [-u username] [-p password]"
      exit 0
      ;;
    -s) SERVER=$2
      ;;
    -d) ALLOWDIRS=$2
      ;;
    -f) ALLOWFILES=$2
      ;;
    -u) USERNAME=$2
      ;;
    -p) PASSWORD=$2
      ;;
    --test) TEST='--test'
      ;;
    --allow_synthetic_data) SYNTH='--synthetic-data'
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

python rtCommon/fileServer.py $USER_PARAM $PASSWD_PARAM -s $SERVER -d $ALLOWDIRS -f $ALLOWFILES $TEST $SYNTH
