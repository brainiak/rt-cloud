#!/usr/bin/env bash

if [ -z $PROJS_DIR ]; then
  if [ -d projects ]; then
    PROJS_DIR=$PWD/projects
  else
    echo "Must set PROJS_DIR env variable or run from directory where projects is a sub-directory"
    exit -1
  fi
fi

echo "docker run -it --rm -v certs:/rt-cloud/certs -v $PROJS_DIR:/rt-cloud/projects -p 8888:8888 brainiak/rtcloud:1.0" "$@"
docker run -it --rm -v certs:/rt-cloud/certs -v $PROJS_DIR:/rt-cloud/projects -p 8888:8888 brainiak/rtcloud:1.0 "$@"
