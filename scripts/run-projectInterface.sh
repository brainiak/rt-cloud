#!/usr/bin/env bash

# get commandline args
args=("${@}")
for i in ${!args[@]}; do
    #echo "$i = ${args[i]}"
    if [[ ${args[i]} = "-ip" ]]; then
      # Get the IP addr value and remove the args from the list
      IP=${args[i+1]}
      unset 'args[i]'
      unset 'args[i+1]'
    elif [[ ${args[i]} = "-h" ]]; then
      echo "USAGE: $0 -p <projectName> [-ip <local_ip_or_hostname>]"
      echo -e "\t[-c <config_toml_file>] [-d <projectDir>]"
      echo -e "\t[--dataRemote] [--subjectRemote] [--remote] [--test]"
      echo -e "\t[-m <main_script>] [-i <initScript>] [-f <finalizeScript>]"
      exit 0
    fi
done

pushd web
npm run build
popd

if [ -z $IP ]; then
    echo "Warning: no ip address supplied, credentials won't be updated"
else
    echo "Adding $IP to ssl cert"
    bash scripts/make-sslcert.sh -ip $IP
fi

# activate rtcloud conda env if needed
if [ -z $CONDA_DEFAULT_ENV ] || [ $CONDA_DEFAULT_ENV != "rtcloud" ]; then
    source ~/.bashrc
    conda activate rtcloud
fi

export PYTHONPATH=./rtCommon/:$PYTHONPATH
echo "python rtCommon/projectServer.py ${args[@]}"
python rtCommon/projectServer.py ${args[@]}
