#!/bin/bash

while test $# -gt 0
do
  case "$1" in
    -ip) IP=$2
      ;;
    -url) URL=$2
      ;;
  esac
  shift
done

if [[ -z $IP && -z $URL ]]; then
  echo "Usage: $0 <-ip ip_address | -url url_address>"
  exit
fi

if [ -z $IP ]; then
  IP='127.0.0.1'
fi

if [ -z $URL ]; then
  URL='localhost'
fi

START_DATE='20190101120000Z'
END_DATE='20240101120000Z'

if [ ! -d "certs" ]; then
  mkdir certs
fi

pushd certs
mkdir -p tmp
# create empty certs index
cat /dev/null > tmp/index.txt
# initialize serial number of certs
echo '01' > tmp/serial.txt

# create the openssl ca config file
cat <<EOF >tmp/ca.config
[ca]
default_ca=CA_default

[CA_default]
database=tmp/index.txt
serial=tmp/serial.txt
policy=policy_match
# new_certs_dir=./

[policy_match]
countryName             = optional
stateOrProvinceName     = optional
localityName            = optional
organizationName        = supplied
organizationalUnitName  = supplied
commonName              = supplied
emailAddress            = optional

[req]
distinguished_name=req_distinguished_name
req_extensions=v3_req
prompt=no

[v3_req]
subjectAltName = @alt_names
#subjectAltName=DNS.1:princeton.edu,DNS.2:localhost,DNS.3:$URL,IP.1:$IP

[alt_names]
DNS.1 = princeton.edu
DNS.2 = localhost
DNS.3 = $URL
IP.1 = $IP

[req_distinguished_name]
C  = "US"
ST = "New Jersey"
L  = "Princeton"
O  = "Princeton University"
OU = "PNI"
CN = "rtcloud.princeton.edu"

EOF

# Make the private key if needed
if [ ! -f rtcloud_private.key ]; then
  openssl genrsa -out rtcloud_private.key 2048
fi

# Note - we need to do this in two steps in order to be able to specify
#  a starting and ending date. Using openssl req -x509 doesn't allow specifying
#  a start date. So we must first create the signing request and then sign with
#  openssl ca -selfsign -new which does allow specifying a start date.

# First create a certificate signing request
openssl req -new -key rtcloud_private.key -sha256 -config tmp/ca.config -out tmp/rtcloud.csr

# Next sign the request
openssl ca -selfsign -md sha256 -batch -outdir ./ -keyfile rtcloud_private.key \
   -config tmp/ca.config -extensions v3_req -startdate $START_DATE -enddate $END_DATE \
   -in tmp/rtcloud.csr -out rtcloud.crt \

popd
