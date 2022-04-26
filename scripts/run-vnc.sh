#!/bin/bash

if [ -z $CONDA_DEFAULT_ENV ] || [ $CONDA_DEFAULT_ENV != "websockify" ]; then
    CONDA_BASE=$(conda info --base)
    source $CONDA_BASE/etc/profile.d/conda.sh
    conda activate websockify
fi

vncserver :1 -localhost -SecurityTypes None &

PYTHONPATH="web" websockify --ssl-only --cert certs/rtcloud.crt --key certs/rtcloud_private.key --auth-plugin websockifyAuth.CookieAuth --auth-source certs/cookie-secret 6080 localhost:5901

vncserver -kill :1
