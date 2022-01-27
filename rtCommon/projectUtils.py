"""
This module contains utility functions used internally by the rtcloud services
"""
import os
import sys
import re
import time
import logging
import getpass
import requests
import threading
import numpy
from pathlib import Path
import rtCommon.utils as utils
from rtCommon.imageHandling import readDicomFromBuffer
from requests.packages.urllib3.contrib import pyopenssl

certFile = 'certs/rtcloud.crt'


def watchForExit():
    '''
    Create a thread which will detect if the parent process exited by
    reading from stdin, when stdin is closed exit this process.
    '''
    exitThread = threading.Thread(name='exitThread', target=processShouldExitThread)
    exitThread.setDaemon(True)
    exitThread.start()


def processShouldExitThread():
    '''
    If this client was spawned by a parent process, then by listening on
    stdin we can tell that the parent process exited when stdin is closed. When
    stdin is closed we can exit this process as well.
    '''
    # print('processShouldExitThread: starting', flush=True)
    while True:
        # logging.info('process should exit loop')
        data = sys.stdin.read()
        if len(data) == 0:
            print('processShouldExitThread: stdin closed, exiting', flush=True)
            os._exit(0)  # - this kills everything immediately
            break
        time.sleep(0.5)


def formatFileData(filename, data):
    """
    Convert raw bytes to a specific memory format such as dicom or matlab data
    """
    fileExtension = Path(filename).suffix
    if fileExtension == '.mat':
        # Matlab file format
        result = utils.loadMatFileFromBuffer(data)
    elif fileExtension == '.dcm':
        # Dicom file format
        result = readDicomFromBuffer(data)
    else:
        result = data
    return result


def login(serverAddr, username, password, testMode=False):
    """
    Logs in to a web service, prompting user for username/password as needed,
    and returns a session_cookie to allow future requests without logging in.
    """
    loginURL = os.path.join('https://', serverAddr, 'login')
    if testMode:
        loginURL = os.path.join('http://', serverAddr, 'login')
        username = 'test'
        password = 'test'
    session = requests.Session()
    session.verify = certFile
    try:
        getResp = session.get(loginURL, timeout=10)
    except Exception:
        raise ConnectionError('Connection error: {}'.format(loginURL))
    if getResp.status_code != 200:
        raise requests.HTTPError('Get URL: {}, returned {}'.format(loginURL, getResp.status_code))
    if username is None:
        print('Login required...')
        username = input('Username: ')
        password = getpass.getpass()
    elif password is None:
        password = getpass.getpass()
    postData = {'name': username, 'password': password, '_xsrf': session.cookies['_xsrf']}
    postResp = session.post(loginURL, postData)
    if postResp.status_code != 200:
        raise requests.HTTPError('Post URL: {}, returned {}'.format(loginURL, postResp.status_code))
    login_cookie = session.cookies.get('login')
    return login_cookie


def checkSSLCertAltName(certFilename, altName):
    """
    Check if altName is list as an alternate server name in the ssl certificate
    """
    with open(certFilename, 'r') as fh:
        certData = fh.read()
    x509 = pyopenssl.OpenSSL.crypto.load_certificate(pyopenssl.OpenSSL.crypto.FILETYPE_PEM, certData)
    altNames = pyopenssl.get_subj_alt_name(x509)
    for _, name in altNames:
        if altName == name:
            return True
    return False


def makeSSLCertFile(serverName):
    logging.info('create sslCert')
    cmd = 'bash scripts/make-sslcert.sh '
    if re.match('^[0-9*]+\.', serverName):
        cmd += ' -ip ' + serverName
    else:
        cmd += ' -url ' + serverName
    success = utils.runCmdCheckOutput(cmd.split(), 'certified until')
    if not success:
        print('Failed to make certificate:')
        sys.exit()


def npToPy(data):
    """
    Converts components in data that are numpy types to regular python types.
    Uses recursive calls to convert nested data structures
    Returns:
        The data structure with numpy elements converted to python types
    """
    if isinstance(data, numpy.generic):
        return data.item()
    elif isinstance(data, dict):
        data2 = {key: npToPy(val) for key, val in data.items()}
        return data2
    elif isinstance(data, list):
        data2 = [npToPy(val) for val in data]
        return data2
    elif isinstance(data, tuple):
        data2 = [npToPy(val) for val in data]
        return tuple(data2)
    elif isinstance(data, set):
        data2 = [npToPy(val) for val in data]
        return set(data2)
    else:
        return data
    # Previous comprehensions, but they weren't recursive
    # args_list = [a.item() if isinstance(a, numpy.generic) else a for a in args]
    # args = tuple(args_list)
    # kwargs = {key: val.item() if isinstance(val, numpy.generic) else val for key, val in kwargs.items()}
