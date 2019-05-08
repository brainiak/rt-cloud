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
      echo "$0 [-c <toml_file>] [-ip <local_ip_or_hostname] [--localfiles]"
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
conda activate rtAtten

python rtCommon/fileServer.py $USER_PARAM $PASSWD_PARAM -s $SERVER -d $ALLOWDIRS -f $ALLOWFILES
