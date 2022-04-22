#!/usr/bin/env bash

# if $PROJ_DIR is not set and --projDir is not provided, then
# no local project directory will be mapped into the docker container

# get commandline args
args=("${@}")
for i in ${!args[@]}; do
    # echo "$i = ${args[i]}"
    if [[ ${args[i]} = "--projDir" ]]; then
      # Get the project directory and remove the args from the list
      PROJ_DIR=${args[i+1]}
      unset 'args[i]'
      unset 'args[i+1]'
    elif [[ ${args[i]} = "-h" ]]; then
      echo "USAGE: $0 --projDir <project-dir-to-map> [list of commands to run in docker image]"
      exit 0
    fi
done

MAP_PARAM=""
if [[ ! -z $PROJ_DIR ]]; then
  PROJ_NAME="$(basename $PROJ_DIR)"
  MAP_PARAM="-v $PROJ_DIR:/rt-cloud/projects/$PROJ_NAME"
fi


echo "docker run -it --rm -v certs:/rt-cloud/certs $MAP_PARAM -p 8888:8888  brainiak/rtcloud:latest" "${args[@]}"
docker run -it --rm -v certs:/rt-cloud/certs $MAP_PARAM -p 8888:8888 -p 6080:6080 brainiak/rtcloud:latest "${args[@]}"
