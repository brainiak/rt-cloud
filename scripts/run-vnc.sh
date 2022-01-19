#!/bin/bash
source ~/.bashrc
conda deactivate
conda activate websockify

vncserver :1 -localhost -SecurityTypes None &

PYTHONPATH="webInterface" websockify --ssl-only --cert certs/rtAtten.crt --key certs/rtAtten_private.key --auth-plugin websockifyAuth.CookieAuth --auth-source certs/cookie-secret 6080 localhost:5901

vncserver -kill :1
