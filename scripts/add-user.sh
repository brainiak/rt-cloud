#!/usr/bin/env bash

# get commandline params
while test $# -gt 0
do
  case "$1" in
    -h)
      echo "$0 [-u username] [-p password]"
      exit 0
      ;;
    -u) USERNAME=$2
      ;;
    -p) PASSWORD=$2
      ;;
  esac
  shift
done

if [ ! -d "certs" ]; then
  mkdir certs
fi

if [ ! -f "certs/passwd" ]; then
  touch certs/passwd
fi

USER_PARAM=''
if [ ! -z $USERNAME ]; then
  USER_PARAM="-u $USERNAME"
fi

PASSWD_PARAM=''
if [ ! -z $PASSWORD ]; then
  PASSWD_PARAM="-p $PASSWORD"
fi

# activate rtcloud conda env if needed
if [ -z $CONDA_DEFAULT_ENV ] || [ $CONDA_DEFAULT_ENV != "rtcloud" ]; then
  source ~/.bashrc
  conda activate rtcloud
fi

python rtCommon/addLogin.py $USER_PARAM $PASSWD_PARAM
