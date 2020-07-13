import os
import sys
import time
import json
import re
import glob
import argparse
import logging
import threading
import websocket
from pathlib import Path
import brainiak.utils.fmrisim_real_time_generator as datagen
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.errors import StateError, RTError
from rtCommon.fileWatcher import FileWatcher
from rtCommon.imageHandling import readDicomFromFile, anonymizeDicom, writeDicomToBuffer
from rtCommon.utils import DebugLevels, findNewestFile, installLoggers
from rtCommon.projectUtils import login, certFile, checkSSLCertAltName, makeSSLCertFile
from rtCommon.projectUtils import generateDataParts, unpackDataMessage

defaultAllowedDirs = ['/tmp', '/data']
defaultAllowedTypes = ['.dcm', '.mat', '.txt']


class WsFileWatcher:
    ''' A server that watches for files on the scanner computer and replies to
        cloud service requests with the file data. The communication connection
        is made with webSockets (ws)
    '''
    fileWatcher = FileWatcher()
    allowedDirs = None
    allowedTypes = None
    serverAddr = None
    sessionCookie = None
    needLogin = True
    shouldExit = False
    validationError = None
    # Synchronizing across threads
    clientLock = threading.Lock()
    fileWatchLock = threading.Lock()

    @staticmethod
    def runFileWatcher(serverAddr, retryInterval=10,
                       allowedDirs=defaultAllowedDirs,
                       allowedTypes=defaultAllowedTypes,
                       username=None, password=None,
                       testMode=False):
        WsFileWatcher.serverAddr = serverAddr
        WsFileWatcher.allowedDirs = allowedDirs
        for i in range(len(allowedTypes)):
            if not allowedTypes[i].startswith('.'):
                allowedTypes[i] = '.' + allowedTypes[i]
        WsFileWatcher.allowedTypes = allowedTypes
        # go into loop trying to do webSocket connection periodically
        WsFileWatcher.shouldExit = False
        while not WsFileWatcher.shouldExit:
            try:
                if WsFileWatcher.needLogin or WsFileWatcher.sessionCookie is None:
                    WsFileWatcher.sessionCookie = login(serverAddr, username, password, testMode=testMode)
                wsAddr = os.path.join('wss://', serverAddr, 'wsData')
                if testMode:
                    print("Warning: using non-encrypted connection for test mode")
                    wsAddr = os.path.join('ws://', serverAddr, 'wsData')
                logging.log(DebugLevels.L6, "Trying connection: %s", wsAddr)
                ws = websocket.WebSocketApp(wsAddr,
                                            on_message=WsFileWatcher.on_message,
                                            on_close=WsFileWatcher.on_close,
                                            on_error=WsFileWatcher.on_error,
                                            cookie="login="+WsFileWatcher.sessionCookie)
                logging.log(logging.INFO, "Connected to: %s", wsAddr)
                print("Connected to: {}".format(wsAddr))
                ws.run_forever(sslopt={"ca_certs": certFile})
            except Exception as err:
                logging.log(logging.INFO, "WSFileWatcher Exception {}: {}".format(type(err).__name__, str(err)))
                print('sleep {}'.format(retryInterval))
                time.sleep(retryInterval)

    @staticmethod
    def stop():
        WsFileWatcher.shouldExit = True

    @staticmethod
    def on_message(client, message):
        fileWatcher = WsFileWatcher.fileWatcher
        response = {'status': 400, 'error': 'unhandled request'}
        try:
            request = json.loads(message)
            response = request.copy()
            if 'data' in response: del response['data']
            cmd = request.get('cmd')
            dir = request.get('dir')
            filename = request.get('filename')
            timeout = request.get('timeout', 0)
            compress = request.get('compress', False)
            logging.log(logging.INFO, "{}: {} {}".format(cmd, dir, filename))
            # Do Validation Checks
            if cmd not in ['getAllowedFileTypes', 'ping', 'error']:
                # All other commands must have a filename or directory parameter
                if dir is None and filename is not None:
                    dir, filename = os.path.split(filename)
                if filename is None:
                    errStr = "{}: Missing filename param".format(cmd)
                    return send_error_response(client, response, errStr)
                if dir is None:
                    errStr = "{}: Missing dir param".format(cmd)
                    return send_error_response(client, response, errStr)
                if cmd in ('watchFile', 'getFile', 'getNewestFile'):
                    if not os.path.isabs(dir):
                        # make path relative to the watch dir
                        dir = os.path.join(fileWatcher.watchDir, dir)
                if WsFileWatcher.validateRequestedFile(dir, filename, cmd) is False:
                    errStr = '{}: {}'.format(cmd, WsFileWatcher.validationError)
                    return send_error_response(client, response, errStr)
                if cmd in ('putTextFile', 'putBinaryFile', 'dataLog'):
                    if not os.path.exists(dir):
                        os.makedirs(dir)
                if not os.path.exists(dir):
                    errStr = '{}: No such directory: {}'.format(cmd, dir)
                    return send_error_response(client, response, errStr)
            # Now handle requests
            if cmd == 'initWatch':
                minFileSize = request.get('minFileSize')
                demoStep = request.get('demoStep')
                if minFileSize is None:
                    errStr = "InitWatch: Missing minFileSize param"
                    return send_error_response(client, response, errStr)
                WsFileWatcher.fileWatchLock.acquire()
                try:
                    fileWatcher.initFileNotifier(dir, filename, minFileSize, demoStep)
                finally:
                    WsFileWatcher.fileWatchLock.release()
                response.update({'status': 200})
                return send_response(client, response)
            elif cmd == 'watchFile':
                WsFileWatcher.fileWatchLock.acquire()
                filename = os.path.join(dir, filename)
                try:
                    retVal = fileWatcher.waitForFile(filename, timeout=timeout)
                finally:
                    WsFileWatcher.fileWatchLock.release()
                if retVal is None:
                    errStr = "WatchFile: 408 Timeout {}s: {}".format(timeout, filename)
                    response.update({'status': 408, 'error': errStr})
                    logging.log(logging.WARNING, errStr)
                    return send_response(client, response)
                else:
                    response.update({'status': 200, 'filename': filename})
                    return send_data_response(client, response, compress)
            elif cmd == 'getFile':
                filename = os.path.join(dir, filename)
                if not os.path.exists(filename):
                    errStr = "GetFile: File not found {}".format(filename)
                    return send_error_response(client, response, errStr)
                response.update({'status': 200, 'filename': filename})
                return send_data_response(client, response, compress)
            elif cmd == 'getNewestFile':
                resultFilename = findNewestFile(dir, filename)
                if resultFilename is None or not os.path.exists(resultFilename):
                    errStr = 'GetNewestFile: file not found: {}'.format(os.path.join(dir, filename))
                    return send_error_response(client, response, errStr)
                response.update({'status': 200, 'filename': resultFilename})
                return send_data_response(client, response, compress)
            elif cmd == 'listFiles':
                if not os.path.isabs(dir):
                    errStr = "listFiles must have an absolute path: {}".format(dir)
                    return send_error_response(client, response, errStr)
                filePattern = os.path.join(dir, filename)
                fileList = [x for x in glob.iglob(filePattern, recursive=True)]
                fileList = WsFileWatcher.filterFileList(fileList)
                response.update({'status': 200, 'filePattern': filePattern, 'fileList': fileList})
                return send_response(client, response)
            elif cmd == 'getAllowedFileTypes':
                response.update({'status': 200, 'fileTypes': WsFileWatcher.allowedTypes})
                return send_response(client, response)
            elif cmd == 'putTextFile':
                text = request.get('text')
                if text is None:
                    errStr = 'PutTextFile: Missing text field'
                    return send_error_response(client, response, errStr)
                elif type(text) is not str:
                    errStr = "PutTextFile: Only text data allowed"
                    return send_error_response(client, response, errStr)
                fullPath = os.path.join(dir, filename)
                with open(fullPath, 'w') as volFile:
                    volFile.write(text)
                response.update({'status': 200})
                return send_response(client, response)
            elif cmd == 'putBinaryFile':
                try:
                    data = unpackDataMessage(request)
                except Exception as err:
                    errStr = 'putBinaryFile: {}'.format(err)
                    return send_error_response(client, response, errStr)
                # If data is None - Incomplete multipart data, more will follow
                if data is not None:
                    fullPath = os.path.join(dir, filename)
                    with open(fullPath, 'wb') as binFile:
                        binFile.write(data)
                response.update({'status': 200})
                return send_response(client, response)
            elif cmd == 'dataLog':
                logLine = request.get('logLine')
                if logLine is None:
                    errStr = 'DataLog: Missing logLine field'
                    return send_error_response(client, response, errStr)
                fullPath = os.path.join(dir, filename)
                with open(fullPath, 'a') as logFile:
                    logFile.write(logLine + '\n')
                response.update({'status': 200})
                return send_response(client, response)
            elif cmd == 'ping':
                response.update({'status': 200})
                return send_response(client, response)
            elif cmd == 'error':
                errorCode = request.get('status', 400)
                errorMsg = request.get('error', 'missing error msg')
                if errorCode == 401:
                    WsFileWatcher.needLogin = True
                    WsFileWatcher.sessionCookie = None
                errStr = 'Error {}: {}'.format(errorCode, errorMsg)
                logging.log(logging.ERROR, errStr)
                return
            else:
                errStr = 'OnMessage: Unrecognized command {}'.format(cmd)
                return send_error_response(client, response, errStr)
        except Exception as err:
            errStr = "OnMessage Exception: {}: {}".format(cmd, err)
            send_error_response(client, response, errStr)
            if cmd == 'error':
                sys.exit()
            return
        errStr = 'unhandled request'
        send_error_response(client, response, errStr)
        return

    @staticmethod
    def on_close(client):
        logging.info('connection closed')

    @staticmethod
    def on_error(client, error):
        if type(error) is KeyboardInterrupt:
            WsFileWatcher.shouldExit = True
        else:
            logging.log(logging.WARNING, "on_error: WSFileWatcher: {} {}".
                        format(type(error), str(error)))

    @staticmethod
    def validateRequestedFile(dir, file, cmd):
        textFileTypeOnly = False
        wildcardAllowed = False
        if cmd in ('putTextFile', 'dataLog'):
            textFileTypeOnly = True
        if cmd in ('listFiles'):
            wildcardAllowed = True
        # Restrict requests to certain directories and file types
        WsFileWatcher.validationError = None
        if WsFileWatcher.allowedDirs is None or WsFileWatcher.allowedTypes is None:
            raise StateError('FileServer: Allowed Directories or File Types is not set')
        if file is not None and file != '':
            fileDir, filename = os.path.split(file)
            fileExtension = Path(filename).suffix
            if textFileTypeOnly:
                if fileExtension != '.txt':
                    WsFileWatcher.validationError = \
                        'Only .txt files allowed with command putTextFile() or dataLog()'
                    return False
            if wildcardAllowed:
                pass  # wildcard searches will be filtered for filetype later
            elif fileExtension not in WsFileWatcher.allowedTypes:
                WsFileWatcher.validationError = \
                    "File type {} not in list of allowed file types {}. " \
                    "Specify allowed filetypes with FileServer -f parameter.". \
                    format(fileExtension, WsFileWatcher.allowedTypes)
                return False
            if fileDir is not None and fileDir != '':  # and os.path.isabs(fileDir):
                dirMatch = False
                for allowedDir in WsFileWatcher.allowedDirs:
                    if fileDir.startswith(allowedDir):
                        dirMatch = True
                        break
                if dirMatch is False:
                    WsFileWatcher.validationError = \
                        "Path {} not within list of allowed directories {}. " \
                        "Make sure you specified a full (absolute) path. " \
                        "Specify allowed directories with FileServer -d parameter.". \
                        format(fileDir, WsFileWatcher.allowedDirs)
                    return False
        if dir is not None and dir != '':
            for allowedDir in WsFileWatcher.allowedDirs:
                if dir.startswith(allowedDir):
                    return True
            WsFileWatcher.validationError = \
                "Path {} not within list of allowed directories {}. " \
                "Make sure you specified a full (absolute) path. " \
                "Specify allowed directories with FileServer -d parameter.". \
                format(dir, WsFileWatcher.allowedDirs)
            return False
        # default case
        return True

    @staticmethod
    def filterFileList(fileList):
        filteredList = []
        for filename in fileList:
            if os.path.isdir(filename):
                continue
            fileExtension = Path(filename).suffix
            if fileExtension in WsFileWatcher.allowedTypes:
                filteredList.append(filename)
        return filteredList


def send_response(client, response):
    WsFileWatcher.clientLock.acquire()
    try:
        client.send(json.dumps(response))
    finally:
        WsFileWatcher.clientLock.release()


def send_error_response(client, response, errStr):
    logging.log(logging.WARNING, errStr)
    response.update({'status': 400, 'error': errStr})
    send_response(client, response)


def send_data_response(client, response, compress=False):
    filename = response.get('filename')
    try:
        data = readFileData(filename)
        if len(data) == 0:
            raise RTError('Empty or zero length file')
    except Exception as err:
        errStr = "readFileData Exception: {}: {}: {}".format(filename, type(err), err)
        return send_error_response(client, response, errStr)
    for msgPart in generateDataParts(data, response, compress):
        send_response(client, msgPart)
    return


def readFileData(filename):
    data = None
    fileExtension = Path(filename).suffix
    if fileExtension == '.dcm':
        # Anonymize Dicom files
        dicomImg = readDicomFromFile(filename)
        dicomImg = anonymizeDicom(dicomImg)
        data = writeDicomToBuffer(dicomImg)
    else:
        with open(filename, 'rb') as fp:
            data = fp.read()
    return data


if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename='logs/fileWatcher.log')
    # do arg parse for server to connect to
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', action="store", dest="server", default="localhost:8888",
                        help="Server Address with Port [server:port]")
    parser.add_argument('-i', action="store", dest="interval", type=int, default=5,
                        help="Retry connection interval (seconds)")
    parser.add_argument('-d', action="store", dest="allowedDirs", default=defaultAllowedDirs,
                        help="Allowed directories to server files from - comma separated list")
    parser.add_argument('-f', action="store", dest="allowedFileTypes", default=defaultAllowedTypes,
                        help="Allowed file types - comma separated list")
    parser.add_argument('-u', '--username', action="store", dest="username", default=None,
                        help="rtcloud website username")
    parser.add_argument('-p', '--password', action="store", dest="password", default=None,
                        help="rtcloud website password")
    parser.add_argument('--test', default=False, action='store_true',
                        help='Use unsecure non-encrypted connection')
    parser.add_argument('--synthetic-data', default=False, action='store_true',
                        help='Generate synthetic data for the run')
    args = parser.parse_args()

    if not re.match(r'.*:\d+', args.server):
        print("Error: Expecting server address in the form <servername:port>")
        parser.print_help()
        sys.exit()

    if type(args.allowedDirs) is str:
        args.allowedDirs = args.allowedDirs.split(',')

    if type(args.allowedFileTypes) is str:
        args.allowedFileTypes = args.allowedFileTypes.split(',')

    addr, port = args.server.split(':')
    # Check if the ssl certificate is valid for this server address
    if checkSSLCertAltName(certFile, addr) is False:
        # Addr not listed in sslCert, recreate ssl Cert
        makeSSLCertFile(addr)

    # if generate synthetic data
    if args.synthetic_data:
        # check if the dicoms are already created
        if not os.path.exists("/tmp/synthetic_dicom/rt_199.dcm"):
            datagen.generate_data("/tmp/synthetic_dicom", {'save_dicom': True})
    
    print("Server: {}, interval {}".format(args.server, args.interval))
    print("Allowed file types {}".format(args.allowedFileTypes))
    print("Allowed directories {}".format(args.allowedDirs))

    WsFileWatcher.runFileWatcher(args.server,
                                 retryInterval=args.interval,
                                 allowedDirs=args.allowedDirs,
                                 allowedTypes=args.allowedFileTypes,
                                 username=args.username,
                                 password=args.password,
                                 testMode=args.test)
