#!/usr/bin/env bash

# if $PROJ_DIR is not set and a -p project_name is provided,
#  then set $PROJ_DIR=$PWD/$project_name
args=("${@}")
for i in ${!args[@]}; do
  if [[ ${args[i]} = "-p" ]] || [[ ${args[i]} = "--projectName" ]]; then
    if [ -z $PROJ_DIR ]; then
      PROJ_DIR=$PWD/${args[i+1]}
    fi
  fi
done

if [ -z $PROJ_DIR ]; then
  echo "Must set PROJ_DIR env variable to point to your project scripts directory"
  exit -1
fi

PROJ_NAME="$(basename $PROJ_DIR)"

echo "docker run -it --rm -v certs:/rt-cloud/certs -v $PROJ_DIR:/rt-cloud/projects/$PROJ_NAME -p 8888:8888  brainiak/rtcloud:latest" "$@"
docker run -it --rm -v certs:/rt-cloud/certs -v $PROJ_DIR:/rt-cloud/projects/$PROJ_NAME -p 8888:8888  brainiak/rtcloud:latest "$@"

