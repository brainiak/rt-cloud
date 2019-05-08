import os
import sys
import re
import json
import time
import logging
import getpass
import requests
import threading
from pathlib import Path
from base64 import b64decode
import rtCommon.utils as utils
from rtCommon.structDict import StructDict
from rtCommon.readDicom import readDicomFromBuffer
from rtCommon.errors import RequestError, StateError
from requests.packages.urllib3.contrib import pyopenssl

certFile = 'certs/rtcloud.crt'


def openWebServerConnection(pipeName):
    '''
    Open a named pipe connection to the local webserver. Open the in and out named pipes.
    Pipe.Open() blocks until the other end opens it as well. Therefore open the reader first
    here and the writer first within the webserver.
    '''
    webpipes = StructDict()
    webpipes.name_in = pipeName + '.toclient'
    webpipes.name_out = pipeName + '.fromclient'
    webpipes.fd_in = open(webpipes.name_in, mode='r')
    webpipes.fd_out = open(webpipes.name_out, mode='w', buffering=1)
    return webpipes


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
    print('processShouldExitThread: starting', flush=True)
    while True:
        # logging.info('process should exit loop')
        data = sys.stdin.read()
        if len(data) == 0:
            print('processShouldExitThread: stdin closed, exiting', flush=True)
            os._exit(0)  # - this kills everything immediately
            break
        time.sleep(0.5)


# Set of helper functions for creating remote file requests
def getFileReqStruct(filename, writefile=False):
    cmd = {'cmd': 'getFile', 'route': 'dataserver', 'filename': filename}
    if writefile is True:
        cmd['writefile'] = True
    return cmd


def getNewestFileReqStruct(filename, writefile=False):
    cmd = {'cmd': 'getNewestFile', 'route': 'dataserver', 'filename': filename}
    if writefile is True:
        cmd['writefile'] = True
    return cmd


def watchFileReqStruct(filename, timeout=5, writefile=False):
    cmd = {'cmd': 'watchFile', 'route': 'dataserver', 'filename': filename, 'timeout': timeout}
    if writefile is True:
        cmd['writefile'] = True
    return cmd


def initWatchReqStruct(dir, filePattern, minFileSize, demoStep=0):
    cmd = {
        'cmd': 'initWatch',
        'route': 'dataserver',
        'dir': dir,
        'filePattern': filePattern,
        'minFileSize': minFileSize
    }
    if demoStep is not None and demoStep > 0:
        cmd['demoStep'] = demoStep
    return cmd


def putTextFileReqStruct(filename, str):
    cmd = {
        'cmd': 'putTextFile',
        'route': 'dataserver',
        'filename': filename,
        'text': str,
    }
    return cmd


def classificationResultStruct(runId, trId, value):
    cmd = {'cmd': 'classificationResult',
           'runId': runId,
           'trId': trId,
           'value': value,
           }
    return cmd


def sendClassicationResult(webpipes, runId, trId, value):
    if webpipes is not None:
        cmd = classificationResultStruct(runId, trId, value)
        clientWebpipeCmd(webpipes, cmd)


def clientWebpipeCmd(webpipes, cmd):
    '''Send a web request using named pipes to the web server for handling.
    This allows a separate client process to make requests of the web server process.
    It writes the request on fd_out and recieves the reply on fd_in.
    '''
    webpipes.fd_out.write(json.dumps(cmd) + os.linesep)
    msg = webpipes.fd_in.readline()
    if len(msg) == 0:
        # fifo closed
        raise StateError('WebPipe closed')
    response = json.loads(msg)
    retVals = StructDict()
    decodedData = None
    if 'status' not in response:
        raise StateError('clientWebpipeCmd: status not in response: {}'.format(response))
    retVals.statusCode = response['status']
    if retVals.statusCode == 200:  # success
        if 'filename' in response:
            retVals.filename = response['filename']
        if 'data' in response:
            decodedData = b64decode(response['data'])
            if retVals.filename is None:
                raise StateError('clientWebpipeCmd: filename field is None')
            retVals.data = formatFileData(retVals.filename, decodedData)
    elif retVals.statusCode not in (200, 408):
        raise RequestError('WebRequest error: status {}: {}'.format(retVals.statusCode, response['error']))
    return retVals


def formatFileData(filename, data):
    '''Convert raw bytes to a specific memory format such as dicom or matlab data'''
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


def login(serverAddr, username, password):
    loginURL = os.path.join('https://', serverAddr, 'login')
    session = requests.Session()
    session.verify = certFile
    try:
        getResp = session.get(loginURL)
    except Exception as err:
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
    return session.cookies['login']


def checkSSLCertAltName(certFilename, altName):
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
