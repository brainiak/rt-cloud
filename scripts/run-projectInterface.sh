#!/usr/bin/env bash

# get commandline args
args=("${@}")
for i in ${!args[@]}; do
    #echo "$i = ${args[i]}"
    if [[ ${args[i]} == "-ip" ]]; then
      # Get the IP addr value and remove the args from the list
      IP=${args[i+1]}
      unset 'args[i]'
      unset 'args[i+1]'
    elif [[ ${args[i]} == "-url" ]]; then
      # Get the url value and remove the args from the list
      URL=${args[i+1]}
      unset 'args[i]'
      unset 'args[i+1]'
    elif [[ ${args[i]} == "-vnc" ]]; then
      # Run the vnc server as well
      VNC=true
      unset 'args[i]'
    elif [[ ${args[i]} == "-h" ]]; then
      echo "USAGE: $0 -p <projectName> [-ip <local_ip_or_hostname>] [-vnc]"
      echo -e "\t[-c <config_toml_file>] [-d <projectDir>]"
      echo -e "\t[--dataRemote] [--subjectRemote] [--remote] [--test]"
      echo -e "\t[-m <main_script>] [-i <initScript>] [-f <finalizeScript>]"
      exit 0
    fi
done

IP_PARAM=""
if [[ ! -z $IP ]]; then
    IP_PARAM="-ip $IP"
fi

URL_PARAM=""
if [[ ! -z $URL ]]; then
    URL_PARAM="-url $URL"
fi

bash scripts/make-sslcert.sh $IP_PARAM $URL_PARAM

if [[ $VNC == true ]]; then
    echo "Starting VNC Server"
    bash scripts/run-vnc.sh &
    VNC_PID=$!
fi

# activate rtcloud conda env if needed
if [ -z $CONDA_DEFAULT_ENV ] || [ $CONDA_DEFAULT_ENV != "rtcloud" ]; then
    CONDA_BASE=$(conda info --base)
    source $CONDA_BASE/etc/profile.d/conda.sh
    conda activate rtcloud
fi

pushd web
npm run build
popd

export PYTHONPATH=./rtCommon/:$PYTHONPATH
echo "python rtCommon/projectServer.py ${args[@]}"
python rtCommon/projectServer.py ${args[@]}

if [[ ! -z $VNC_PID ]]; then
  # kill $VNC_PID
  vncserver -kill :1
fi