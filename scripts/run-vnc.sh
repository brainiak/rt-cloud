#!/bin/bash
source ~/.bashrc
conda deactivate
conda activate websockify

vncserver :1 -localhost -SecurityTypes None &

PYTHONPATH="web" websockify --ssl-only --cert certs/rtcloud.crt --key certs/rtcloud_private.key --auth-plugin websockifyAuth.CookieAuth --auth-source certs/cookie-secret 6080 localhost:5901

vncserver -kill :1
