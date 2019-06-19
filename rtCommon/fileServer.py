import os
import sys
import time
import json
import re
import argparse
import logging
import threading
import websocket
from base64 import b64encode
from base64 import b64decode
from pathlib import Path
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.errors import StateError
from rtCommon.fileWatcher import FileWatcher
from rtCommon.readDicom import readDicomFromFile, anonymizeDicom, writeDicomToBuffer
from rtCommon.utils import DebugLevels, findNewestFile, installLoggers
from rtCommon.webClientUtils import login, certFile, checkSSLCertAltName, makeSSLCertFile

defaultAllowedDirs = ['/tmp', '/data']
defaultAllowedTypes = ['.dcm', '.mat']


class WebSocketFileWatcher:
    ''' A server that watches for files on the scanner computer and replies to
        cloud service requests with the file data.
    '''
    fileWatcher = FileWatcher()
    allowedDirs = None
    allowedTypes = None
    serverAddr = None
    sessionCookie = None
    needLogin = True
    shouldExit = False
    # Synchronizing across threads
    clientLock = threading.Lock()
    fileWatchLock = threading.Lock()

    @staticmethod
    def runFileWatcher(serverAddr, retryInterval=10, allowedDirs=defaultAllowedDirs,
                       allowedTypes=defaultAllowedTypes, username=None, password=None):
        WebSocketFileWatcher.serverAddr = serverAddr
        WebSocketFileWatcher.allowedDirs = allowedDirs
        for i in range(len(allowedTypes)):
            if not allowedTypes[i].startswith('.'):
                allowedTypes[i] = '.' + allowedTypes[i]
        WebSocketFileWatcher.allowedTypes = allowedTypes
        # go into loop trying to do webSocket connection periodically
        while not WebSocketFileWatcher.shouldExit:
            try:
                if WebSocketFileWatcher.needLogin or WebSocketFileWatcher.sessionCookie is None:
                    WebSocketFileWatcher.sessionCookie = login(serverAddr, username, password)
                wsAddr = os.path.join('wss://', serverAddr, 'wsData')
                logging.log(DebugLevels.L6, "Trying connection: %s", wsAddr)
                ws = websocket.WebSocketApp(wsAddr,
                                            on_message=WebSocketFileWatcher.on_message,
                                            on_close=WebSocketFileWatcher.on_close,
                                            on_error=WebSocketFileWatcher.on_error,
                                            cookie="login="+WebSocketFileWatcher.sessionCookie)
                logging.log(logging.INFO, "Connected to: %s", wsAddr)
                print("Connected to: {}".format(wsAddr))
                ws.run_forever(sslopt={"ca_certs": certFile})
            except Exception as err:
                logging.log(logging.INFO, "WSFileWatcher Exception {}: {}".format(type(err).__name__, str(err)))
                time.sleep(retryInterval)

    @staticmethod
    def on_message(client, message):
        fileWatcher = WebSocketFileWatcher.fileWatcher
        response = {'status': 400, 'error': 'unhandled request'}
        try:
            request = json.loads(message)
            cmd = request['cmd']
            if cmd == 'initWatch':
                dir = request['dir']
                filePattern = request['filePattern']
                minFileSize = request['minFileSize']
                demoStep = request.get('demoStep')
                logging.log(logging.INFO, "initWatch: %s, %s, %d", dir, filePattern, minFileSize)
                if dir is None or filePattern is None or minFileSize is None:
                    errStr = "InitWatch: Missing file information: {} {}".format(dir, filePattern)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif WebSocketFileWatcher.validateRequestedFile(dir, None) is False:
                    errStr = 'InitWatch: Non-allowed directory {}'.format(dir)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif not os.path.exists(dir):
                    errStr = 'InitWatch: No such directory: {}'.format(dir)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                else:
                    WebSocketFileWatcher.fileWatchLock.acquire()
                    try:
                        fileWatcher.initFileNotifier(dir, filePattern, minFileSize, demoStep)
                    finally:
                        WebSocketFileWatcher.fileWatchLock.release()
                    response = {'status': 200}
            elif cmd == 'watchFile':
                filename = request['filename']
                timeout = request['timeout']
                logging.log(logging.INFO, "watchFile: %s", filename)
                if filename is None:
                    errStr = 'WatchFile: Missing filename'
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif WebSocketFileWatcher.validateRequestedFile(None, filename) is False:
                    errStr = 'WatchFile: Non-allowed file {}'.format(filename)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                else:
                    WebSocketFileWatcher.fileWatchLock.acquire()
                    try:
                        retVal = fileWatcher.waitForFile(filename, timeout=timeout)
                    finally:
                        WebSocketFileWatcher.fileWatchLock.release()
                    if retVal is None:
                        errStr = "WatchFile: 408 Timeout {}s: {}".format(timeout, filename)
                        response = {'status': 408, 'error': errStr}
                        logging.log(logging.WARNING, errStr)
                    else:
                        # TODO - may need some retry logic here if the file was read
                        #  before it was completely written. Maybe checking filesize
                        #  against data size.
                        data = readFile(filename)
                        b64Data = b64encode(data)
                        b64StrData = b64Data.decode('utf-8')
                        response = {'status': 200, 'filename': filename, 'data': b64StrData}
            elif cmd == 'getFile':
                filename = request['filename']
                if filename is not None and not os.path.isabs(filename):
                    # relative path to the watch dir
                    filename = os.path.join(fileWatcher.watchDir, filename)
                logging.log(logging.INFO, "getFile: %s", filename)
                if filename is None:
                    errStr = "GetFile: Missing filename"
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif WebSocketFileWatcher.validateRequestedFile(None, filename) is False:
                    errStr = 'GetFile: Non-allowed file {}'.format(filename)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif not os.path.exists(filename):
                    errStr = "GetFile: File not found {}".format(filename)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                else:
                    data = readFile(filename)
                    b64Data = b64encode(data)
                    b64StrData = b64Data.decode('utf-8')
                    response = {'status': 200, 'filename': filename, 'data': b64StrData}
            elif cmd == 'getNewestFile':
                filename = request['filename']
                logging.log(logging.INFO, "getNewestFile: %s", filename)
                if filename is None:
                    errStr = "GetNewestFile: Missing filename"
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif WebSocketFileWatcher.validateRequestedFile(None, filename) is False:
                    errStr = 'GetNewestFile: Non-allowed file {}'.format(filename)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                else:
                    baseDir, filePattern = os.path.split(filename)
                    if not os.path.isabs(baseDir):
                        # relative path to the watch dir
                        baseDir = os.path.join(fileWatcher.watchDir, baseDir)
                    filename = findNewestFile(baseDir, filePattern)
                    if filename is None or not os.path.exists(filename):
                        errStr = 'GetNewestFile: file not found: {}'.format(os.path.join(baseDir, filePattern))
                        response = {'status': 400, 'error': errStr}
                        logging.log(logging.WARNING, errStr)
                    else:
                        data = readFile(filename)
                        b64Data = b64encode(data)
                        b64StrData = b64Data.decode('utf-8')
                        response = {'status': 200, 'filename': filename, 'data': b64StrData}
            elif cmd == 'ping':
                response = {'status': 200}
            elif cmd == 'putTextFile':
                filename = request['filename']
                text = request['text']
                logging.log(logging.INFO, "putTextFile: %s", filename)
                if filename is None:
                    errStr = 'PutTextFile: Missing filename field'
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif text is None:
                    errStr = 'PutTextFile: Missing text field'
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif WebSocketFileWatcher.validateRequestedFile(None, filename, textFileTypeOnly=True) is False:
                    errStr = 'PutTextFile: Non-allowed file {}'.format(filename)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif type(text) is not str:
                    errStr = "PutTextFile: Only text allowed"
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                else:
                    outputDir = os.path.dirname(filename)
                    if not os.path.exists(outputDir):
                        os.makedirs(outputDir)
                    # print('putTextFile: write {}'.format(filename))
                    with open(filename, 'w+') as volFile:
                        volFile.write(text)
                    response = {'status': 200}
            elif cmd == 'putBinaryFile':
                filename = request['filename']
                encodedData = request['data']
                logging.log(logging.INFO, "PutBinaryFile: %s", filename)
                if filename is None:
                    errStr = 'PutBinaryFile: Missing filename field'
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif encodedData is None:
                    errStr = 'PutBinaryFile: Missing data field'
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif WebSocketFileWatcher.validateRequestedFile(None, filename) is False:
                    errStr = 'PutBinaryFile: Non-allowed file {}'.format(filename)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                else:
                    data = b64decode(encodedData)
                    outputDir = os.path.dirname(filename)
                    if not os.path.exists(outputDir):
                        os.makedirs(outputDir)
                    with open(filename, 'wb+') as binFile:
                        binFile.write(data)
                    response = {'status': 200}
            elif cmd == 'dataLog':
                filename = request['filename']
                logging.log(logging.INFO, "dataLog: %s", filename)
                logLine = request['logLine']
                if filename is None:
                    errStr = 'DataLog: Missing filename field'
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif logLine is None:
                    errStr = 'DataLog: Missing logLine field'
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                elif WebSocketFileWatcher.validateRequestedFile(None, filename, textFileTypeOnly=True) is False:
                    errStr = 'DataLog: Non-allowed file {}'.format(filename)
                    response = {'status': 400, 'error': errStr}
                    logging.log(logging.WARNING, errStr)
                else:
                    with open(filename, 'a+') as logFile:
                        logFile.write(logLine + '\n')
                    response = {'status': 200}
            elif cmd == 'error':
                errorCode = request['status']
                if errorCode == 401:
                    WebSocketFileWatcher.needLogin = True
                    WebSocketFileWatcher.sessionCookie = None
                errStr = 'Error {}: {}'.format(errorCode, request['error'])
                logging.log(logging.ERROR, request['error'])
                return
            else:
                errStr = 'OnMessage: Unrecognized command {}'.format(cmd)
                response = {'status': 400, 'error': errStr}
                logging.log(logging.WARNING, errStr)
        except Exception as err:
            errStr = "OnMessage Exception: {}: {}".format(cmd, err)
            logging.log(logging.WARNING, errStr)
            response = {'status': 400, 'error': errStr}
            if cmd == 'error':
                sys.exit()
        # merge response into the request dictionary
        request.update(response)
        response = request
        WebSocketFileWatcher.clientLock.acquire()
        try:
            client.send(json.dumps(response))
        finally:
            WebSocketFileWatcher.clientLock.release()

    @staticmethod
    def on_close(client):
        logging.info('connection closed')

    @staticmethod
    def on_error(client, error):
        if type(error) is KeyboardInterrupt:
            WebSocketFileWatcher.shouldExit = True
        else:
            logging.log(logging.WARNING, "on_error: WSFileWatcher: {} {}".
                        format(type(error), str(error)))

    @staticmethod
    def validateRequestedFile(dir, file, textFileTypeOnly=False):
        # Restrict requests to certain directories and file types
        if WebSocketFileWatcher.allowedDirs is None or WebSocketFileWatcher.allowedTypes is None:
            raise StateError('Allowed Directories or File Types is not set')
        if file is not None and file != '':
            fileDir, filename = os.path.split(file)
            fileExtension = Path(filename).suffix
            if textFileTypeOnly:
                if fileExtension != '.txt':
                    return False
            elif fileExtension not in WebSocketFileWatcher.allowedTypes:
                return False
            if fileDir is not None and fileDir != '':  # and os.path.isabs(fileDir):
                dirMatch = False
                for allowedDir in WebSocketFileWatcher.allowedDirs:
                    if fileDir.startswith(allowedDir):
                        dirMatch = True
                        break
                if dirMatch is False:
                    return False
        if dir is not None and dir != '':
            for allowedDir in WebSocketFileWatcher.allowedDirs:
                if dir.startswith(allowedDir):
                    return True
            return False
        # default case
        return True


def readFile(filename):
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
                        help="Server Address")
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
    args = parser.parse_args()

    if not re.match(r'.*:\d+', args.server):
        print("Usage: Expecting server address in the form <servername:port>")
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

    print("Server: {}, interval {}".format(args.server, args.interval))
    print("Allowed file types {}".format(args.allowedFileTypes))
    print("Allowed directories {}".format(args.allowedDirs))

    WebSocketFileWatcher.runFileWatcher(args.server,
                                        retryInterval=args.interval,
                                        allowedDirs=args.allowedDirs,
                                        allowedTypes=args.allowedFileTypes,
                                        username=args.username,
                                        password=args.password)
