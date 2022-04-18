"""
Utility functions for using ssl encrypted web connections
"""
import os
import ssl
import logging
from .errors import ValidationError

currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)

certsDir = os.path.join(rootPath, 'certs')
sslCertFile = 'rtcloud.crt'
sslPrivateKey = 'rtcloud_private.key'

def getSslCertFilePath():
    global certsDir, sslCertFile
    certfile = os.path.join(certsDir, sslCertFile)
    if os.path.exists(certfile):
        return certfile
    logging.info("Cert not found in local certs dir: {}".format(certfile))
    paths = ssl.get_default_verify_paths()
    certfile = os.path.join(paths.capath, sslCertFile)
    if not os.path.exists(certfile):
        raise ValidationError("SSL Cert paths not found for {}".format(certfile))
    return certfile


def getSslKeyFilePath():
    global certsDir, sslPrivateKey
    keyfile = os.path.join(certsDir, sslPrivateKey)
    if os.path.exists(keyfile):
        return keyfile
    logging.info("Key not found in local certs dir: {}".format(keyfile))
    paths = ssl.get_default_verify_paths()
    keyfile = os.path.join(os.path.dirname(paths.capath), 'private/', sslPrivateKey)
    if not os.path.exists(keyfile):
        raise ValidationError("SSL Cert paths not found for {}".format(sslPrivateKey))
    return keyfile
