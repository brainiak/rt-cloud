import os
import sys
import re
import json
import time
import zlib
import glob
import hashlib
import logging
import getpass
import requests
import threading
from pathlib import Path
from base64 import b64encode, b64decode
import rtCommon.utils as utils
from rtCommon.structDict import StructDict
from rtCommon.readDicom import readDicomFromBuffer
from rtCommon.errors import RequestError, StateError, ValidationError
from requests.packages.urllib3.contrib import pyopenssl

certFile = 'certs/rtcloud.crt'
defaultPipeName = 'rt_pipe_default'

# Cache of multi-part data transfers in progress
multiPartDataCache = {}
dataPartSize = 10 * (2**20)


def openNamedPipe(pipeName):
    '''
    Open a named pipe connection to the local projectInterface. Open the in and out named pipes.
    Pipe.Open() blocks until the other end opens it as well. Therefore open the reader first
    here and the writer first within the projectInterface.
    '''
    commPipes = makeFifo(pipename=pipeName, isServer=False)
    commPipes.fd_in = open(commPipes.name_in, mode='r')
    commPipes.fd_out = open(commPipes.name_out, mode='w', buffering=1)
    return commPipes


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


# Set of helper functions for creating remote file requests
def getFileReqStruct(filename, compress=False):
    cmd = {'cmd': 'getFile',
           'route': 'dataserver',
           'filename': filename,
           'compress': compress}
    return cmd


def getNewestFileReqStruct(filename, compress=False):
    cmd = {'cmd': 'getNewestFile',
           'route': 'dataserver',
           'filename': filename,
           'compress': compress}
    return cmd


def listFilesReqStruct(filePattern):
    cmd = {'cmd': 'listFiles', 'route': 'dataserver', 'filename': filePattern}
    return cmd


def watchFileReqStruct(filename, timeout=5, compress=False):
    cmd = {'cmd': 'watchFile',
           'route': 'dataserver',
           'filename': filename,
           'timeout': timeout,
           'compress': compress}
    return cmd


def initWatchReqStruct(dir, filePattern, minFileSize, demoStep=0):
    cmd = {
        'cmd': 'initWatch',
        'route': 'dataserver',
        'dir': dir,
        'filename': filePattern,
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


def putBinaryFileReqStruct(filename):
    cmd = {
        'cmd': 'putBinaryFile',
        'route': 'dataserver',
        'filename': filename,
    }
    return cmd


def resultStruct(runId, trId, value):
    cmd = {'cmd': 'resultValue',
           'runId': runId,
           'trId': trId,
           'value': value,
           }
    return cmd


def initProjectComm(commPipeName, filesRemote):
    projComm = None
    if commPipeName:
        # Process is being run from a projectInterface
        # Watch for parent process exiting and then exit when it does
        watchForExit()
    # If filesremote is true, must create a projComm connecton to the projectInterface to retrieve the files
    # If filesremote is false, but runing from a projectInterface, still need a projComm connection to return logging output
    # Only when local files is specified and script is not run from a projectInterface is no projComm connection needed
    if filesRemote:
        # Must have a projComm for remote files
        if commPipeName is None:
            # No pipe name specified, use default name
            commPipeName = defaultPipeName
    if commPipeName:
        projComm = openNamedPipe(commPipeName)
    return projComm


def sendResultToWeb(commPipes, runId, trId, value):
    if commPipes is not None:
        cmd = resultStruct(runId, trId, value)
        clientSendCmd(commPipes, cmd)


def uploadFilesToCloud(fileInterface, srcFilePattern, outputDir):
    # get the list of files to upload
    fileList = fileInterface.listFiles(srcFilePattern)
    for file in fileList:
        dir, filename = os.path.split(file)
        data = fileInterface.getFile(file)
        outputFilename = os.path.normpath(outputDir + '/' + filename)
        logging.info('upload: {}/{} --> {}'.format(dir, filename, outputFilename))
        utils.writeFile(outputFilename, data)


def downloadFilesFromCloud(fileInterface, srcFilePattern, outputDir):
    fileList = [x for x in glob.iglob(srcFilePattern)]
    for file in fileList:
        with open(file, 'rb') as fp:
            data = fp.read()
        dir, filename = os.path.split(file)
        outputFilename = os.path.normpath(outputDir + '/' + filename)
        logging.info('download: {} --> {}'.format(file, outputFilename))
        fileInterface.putBinaryFile(outputFilename, data)
    return


def clientSendCmd(commPipes, cmd):
    '''Send a request using named pipes to the projectInterface for handling.
    This allows a separate client process to make requests of the projectInterface process.
    It writes the request on fd_out and recieves the reply on fd_in.
    '''
    data = None
    savedError = None
    incomplete = True
    while incomplete:
        commPipes.fd_out.write(json.dumps(cmd) + os.linesep)
        msg = commPipes.fd_in.readline()
        if len(msg) == 0:
            # fifo closed
            raise StateError('commPipe closed')
        response = json.loads(msg)
        status = response.get('status', -1)
        if status != 200:
            raise RequestError('clientSendCmd: Cmd: {} status {}: error {}'.
                               format(cmd.get('cmd'), status, response.get('error')))
        if 'data' in response:
            try:
                data = unpackDataMessage(response)
            except Exception as err:
                # The call may be incomplete, save the error and keep receiving as needed
                logging.error('clientSendCmd: {}'.format(err))
                if savedError is None:
                    savedError = err
            cmd['callId'] = response.get('callId', -1)
        # Check if need to continue to get more parts
        incomplete = response.get('incomplete', False)
    if savedError:
        raise RequestError('clientSendCmd: {}'.format(savedError))
    retVals = StructDict()
    retVals.statusCode = response.get('status', -1)
    if 'filename' in response:
        retVals.filename = response['filename']
    if 'fileList' in response:
        retVals.fileList = response['fileList']
    if data:
        retVals.data = data
        if retVals.filename is None:
            raise StateError('clientSendCmd: filename field is None')
    return retVals


def generateDataParts(data, msg, compress):
    dataSize = len(data)
    # update message for all data parts with the following info
    numParts = (dataSize + dataPartSize - 1) // dataPartSize
    msg['status'] = 200
    msg['fileSize'] = dataSize
    msg['fileHash'] = hashlib.md5(data).hexdigest()
    msg['numParts'] = numParts
    if numParts > 1:
        msg['multipart'] = True
    i = 0
    partId = 0
    dataSize = len(data)
    while i < dataSize:
        msgPart = msg.copy()
        partId += 1
        sendSize = dataSize - i
        if sendSize > dataPartSize:
            sendSize = dataPartSize
        dataPart = data[i:i+sendSize]
        msgPart['partId'] = partId
        try:
            msgPart = encodeMessageData(msgPart, dataPart, compress)
        except Exception as err:
            msgPart['status'] = 400
            msgPart['error'] = str(err)
            yield msgPart
            break
        yield msgPart
        i += sendSize
    return


def encodeMessageData(message, data, compress):
    message['hash'] = hashlib.md5(data).hexdigest()
    dataSize = len(data)
    if compress or dataSize > (20*2**20):
        message['compressed'] = True
        data = zlib.compress(data)
    message['data'] = b64encode(data).decode('utf-8')
    message['dataSize'] = dataSize
    # if 'compressed' in message:
    #     print('Compression ratio: {:.2f}'.format(len(message['data'])/dataSize))
    if len(message['data']) > 100*1024*1024:
        message['data'] = None
        raise ValidationError('encodeMessageData: encoded file exceeds max size of 100MB')
    return message


def decodeMessageData(message):
    data = None
    if 'data' not in message:
        raise RequestError('decodeMessageData: data field not in response')
    decodedData = b64decode(message['data'])
    if 'compressed' in message:
        data = zlib.decompress(decodedData)
    else:
        data = decodedData
    if 'hash' in message:
        dataHash = hashlib.md5(data).hexdigest()
        if dataHash != message['hash']:
            raise RequestError('decodeMessageData: Hash checksum mismatch {} {}'.
                               format(dataHash, message['hash']))
    return data


def unpackDataMessage(msg):
    global multiPartDataCache
    try:
        if msg.get('status') != 200:
            # On error delete any partial transfers
            fileHash = msg.get('fileHash')
            if fileHash is not None and fileHash in multiPartDataCache:
                del multiPartDataCache[fileHash]
            raise RequestError('unpackDataMessage: {} {}'.format(msg.get('status'), msg.get('error')))
        data = decodeMessageData(msg)
        multipart = msg.get('multipart', False)
        numParts = msg.get('numParts', 1)
        partId = msg.get('partId', 1)
        logging.debug('unpackDataMessage: callid {}, part {} of {}'.format(msg.get('callId'), partId, numParts))
        if multipart is False or numParts == 1:
            # All data sent in a single message
            return data
        else:
            assert numParts > 1
            assert multipart is True
            if partId > numParts:
                raise RequestError(
                    'unpackDataMessage: Inconsistent parts: partId {} exceeds numParts {}'.
                    format(partId, numParts))
            # get the data structure for this data
            fileHash = msg.get('fileHash')
            if partId > 1:
                partialDataStruct = multiPartDataCache.get(fileHash)
                if partialDataStruct is None:
                    raise RequestError('unpackDataMessage: partialDataStruct not found')
            else:
                partialDataStruct = StructDict({'cachedDataParts': [None]*numParts, 'numCachedParts': 0})
                multiPartDataCache[fileHash] = partialDataStruct
            partialDataStruct.cachedDataParts[partId-1] = data
            partialDataStruct.numCachedParts += 1
            if partialDataStruct.numCachedParts == numParts:
                # All parts of the multipart transfer have been received
                # Concatenate the data into one bytearray
                data = bytearray()
                for i in range(numParts):
                    dataPart = partialDataStruct.cachedDataParts[i]
                    if dataPart is None:
                        raise StateError('unpackDataMessage: missing dataPart {}'.format(i))
                    data.extend(dataPart)
                # Check fileHash and fileSize
                dataHash = hashlib.md5(data).hexdigest()
                dataSize = len(data)
                if dataHash != fileHash:
                    raise RequestError("unpackDataMessage: File checksum mismatch {} {}".
                                       format(dataHash, fileHash))
                if dataSize != msg.get('fileSize', 0):
                    raise RequestError("unpackDataMessage: File size mismatch {} {}".
                                       format(dataSize, msg.get('fileSize', 0)))
                # delete the multipart data cache for this item
                del multiPartDataCache[fileHash]
                return data
        # Multi-part transfer not complete, nothing to return
        return None
    except Exception as err:
        # removed any cached data
        fileHash = msg.get('fileHash')
        if fileHash and fileHash in multiPartDataCache:
            del multiPartDataCache[fileHash]
        raise err


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


def login(serverAddr, username, password, testMode=False):
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


def makeFifo(pipename=None, isServer=True):
    fifodir = '/tmp/pipes/'
    if not os.path.exists(fifodir):
        os.makedirs(fifodir)
    # create new pipe
    if pipename is None:
        fifoname = os.path.join(fifodir, 'comm_pipe_{}'.format(int(time.time())))
        if isServer:
            # remove previous temporary named pipes
            for p in Path(fifodir).glob("comm_pipe_*"):
                p.unlink()
    else:
        fifoname = os.path.join(fifodir, pipename)
    # fifo stuct
    commPipes = StructDict()
    if isServer:
        commPipes.name_out = fifoname + '.toclient'
        commPipes.name_in = fifoname + '.fromclient'
    else:
        commPipes.name_out = fifoname + '.fromclient'
        commPipes.name_in = fifoname + '.toclient'

    if not os.path.exists(commPipes.name_out):
        os.mkfifo(commPipes.name_out)
    if not os.path.exists(commPipes.name_in):
        os.mkfifo(commPipes.name_in)
    commPipes.fifoname = fifoname
    return commPipes
