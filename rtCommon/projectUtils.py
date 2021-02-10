"""
This module contains utility functions used internally by the rtcloud services
"""
import os
import sys
import re
import time
import zlib
import hashlib
import logging
import getpass
import requests
import threading
import numpy
from pathlib import Path
from base64 import b64encode, b64decode
import rtCommon.utils as utils
from rtCommon.structDict import StructDict
from rtCommon.imageHandling import readDicomFromBuffer
from rtCommon.errors import RequestError, StateError, ValidationError
from requests.packages.urllib3.contrib import pyopenssl

certFile = 'certs/rtcloud.crt'

# Cache of multi-part data transfers in progress
multiPartDataCache = {}
dataPartSize = 10 * (2**20)


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


def generateDataParts(data, msg, compress):
    """
    A python "generator" that, for data > 10 MB, will create multi-part
    messages of 10MB each to send the data incrementally
    Args:
        data (bytes): data to send
        msg (dict): message header for the request
        compress (bool): whether to compress the data befor sending
    Returns:
        Repeated calls return the next partial message to be sent until
            None is returned
    """
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
    """
    b64 encode binary data in preparation for sending. Updates the message header
    as needed
    Args:
        message (dict): message header
        data (bytes): binary data
        compress (bool): whether to compress binary data
    Returns:
        Modified message dict with appropriate fields filled in
    """
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
    """
    Given a message encoded with encodeMessageData (above), decode that message.
    Validate and retrive orignal bytes.
    Args:
        message (dict): encoded message to decode
    Returns:
        The byte data of the original message from the sender
    """
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
    """
    Handles receiving multipart (an singlepart) data messages and returns the data bytes.
    In the case of multipart messages a data cache is used to store intermediate parts
    until all parts are received and the final data can be reconstructed.
    Args:
        msg (dict): Potentially on part of a multipart message to unpack
    Returns:
        None if not all multipart messages have been received yet, or
        Data bytes if all multipart messages have been received.
    """
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
