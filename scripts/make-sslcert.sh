#!/bin/bash

while test $# -gt 0
do
  case "$1" in
    -ip) IP=$2
      ;;
    -url) URL=$2
      ;;
    -h)
      echo "Usage: $0 [-ip ip_address] [-url url_address]"
      echo "Creates the ssl certificate rtcloud.crt and optionally adds"
      echo "ip_address and/or url_address to the subject alternate names."
      exit
      ;;
  esac
  shift
done

if [ -z $IP ]; then
  IP='127.0.0.1'
fi

if [ -z $URL ]; then
  URL='localhost'
fi

# certificate will expire one year from Jan 1 of current year
# some browsers require certificates to expire after a year
current_year="`date +%Y`"
START_DATE=$current_year"0101120000Z"
END_DATE=$(($current_year + 1))"0101120000Z"

if [ ! -d "certs" ]; then
  mkdir certs
fi

pushd certs
mkdir -p tmp
# create empty certs index
cat /dev/null > tmp/index.txt
# initialize serial number of certs
echo '1000' > tmp/serial.txt

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
distinguished_name = req_distinguished_name
req_extensions = v3_req
x509_extensions = v3_req
default_md = sha256
prompt=no

[v3_req]
basicConstraints=CA:TRUE
subjectAltName = @alt_names
#subjectAltName=DNS.1:princeton.edu,DNS.2:localhost,DNS.3:$URL,IP.1:127.0.0.1,IP.2:$IP

[alt_names]
DNS.1 = princeton.edu
DNS.2 = localhost
DNS.3 = $URL
IP.1 = 127.0.0.1
IP.2 = $IP

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
# We want a consistent starting and ending date so recreating the ssl certificate
#   with a different IP address in the SubjectAlternateNames section will still
#   match previously made certificates.

# First create a certificate signing request
openssl req -new -key rtcloud_private.key -sha256 -config tmp/ca.config -out tmp/rtcloud.csr

# Next sign the request
openssl ca -selfsign -md sha256 -batch -outdir ./ -keyfile rtcloud_private.key \
   -config tmp/ca.config -extensions v3_req -startdate $START_DATE -enddate $END_DATE \
   -in tmp/rtcloud.csr -out rtcloud.crt

# Print hashes
# GNU uses md5sum but Macs may only have md5
if ! command -v md5sum
then
  echo "ssl cert id: " $(md5 rtcloud.crt)
  echo "ssl key id: " $(md5 rtcloud_private.key)
else
  echo "ssl cert id: " $(md5sum rtcloud.crt)
  echo "ssl key id: " $(md5sum rtcloud_private.key)
fi

popd
