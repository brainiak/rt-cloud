import tornado.web
import tornado.websocket
import os
import time
import ssl
import json
import queue
import logging
import re
import toml
import shlex
import uuid
import bcrypt
import numbers
import asyncio
import threading
import subprocess
from pathlib import Path
from rtCommon.projectUtils import listFilesReqStruct, getFileReqStruct, decodeMessageData
from rtCommon.projectUtils import defaultPipeName, makeFifo, unpackDataMessage
from rtCommon.structDict import StructDict, recurseCreateStructDict
from rtCommon.certsUtils import getCertPath, getKeyPath
from rtCommon.utils import DebugLevels, writeFile, loadConfigFile
from rtCommon.errors import StateError, RequestError, RTError
from rtCommon.webHandlers import HttpHandler, LoginHandler, LogoutHandler, certsDir
from rtCommon.webSocketHandlers import BaseWebSocketHandler, DataWebSocketHandler, \
    RequestHandler, sendWebSocketMessage, closeAllConnections

sslCertFile = 'rtcloud.crt'
sslPrivateKey = 'rtcloud_private.key'
CommonOutputDir = '/rtfmriData/'


moduleDir = os.path.dirname(os.path.realpath(__file__))
rootDir = os.path.dirname(moduleDir)

# Note: User refers to the clinician running the experiment, so userWindow is the main
#  browser window for running the experiment.


class Web():
    ''' Cloud service web-interface that is the front-end to the data processing. '''
    app = None
    httpServer = None
    httpPort = 8888
    # Callback functions to invoke when message received from client window connection
    browserMainCallback = None
    # Main html page to load
    webDir = os.path.join(rootDir, 'web/')
    confDir = os.path.join(webDir, 'conf/')
    htmlDir = os.path.join(webDir, 'html')
    webIndexPage = 'index.html'
    webLoginPage = 'login.html'
    webBiofeedPage = 'biofeedback.html'
    # Synchronizing across threads
    ioLoopInst = None
    filesremote = False
    fmriPyScript = None
    initScript = None
    finalizeScript = None
    configFilename = None
    cfg = None
    testMode = False
    runInfo = StructDict({'threadId': None, 'stopRun': False})
    resultVals = [[{'x': 0, 'y': 0}]]
    dataRequestHandler = RequestHandler('wsData')

    @staticmethod
    def start(params, cfg, testMode=False):
        if Web.app is not None:
            raise RuntimeError("Web Server already running.")
        Web.testMode = testMode
        # Set default value before checking for param overrides
        Web.browserMainCallback = defaultBrowserMainCallback
        if params.browserMainCallback:
            Web.browserMainCallback = params.browserMainCallback
        if params.htmlDir:
            Web.htmlDir = params.htmlDir
            Web.webDir = os.path.dirname(Web.htmlDir)
        if params.port:
            Web.httpPort = params.port
        Web.fmriPyScript = params.fmriPyScript
        Web.initScript = params.initScript
        Web.finalizeScript = params.finalizeScript
        Web.filesremote = params.filesremote
        if type(cfg) is str:
            Web.configFilename = cfg
            cfg = loadConfigFile(Web.configFilename)
        Web.cfg = cfg
        if not os.path.exists(Web.confDir):
            os.makedirs(Web.confDir)
        src_root = os.path.join(Web.webDir, 'src')
        css_root = os.path.join(Web.webDir, 'css')
        img_root = os.path.join(Web.webDir, 'img')
        build_root = os.path.join(Web.webDir, 'build')
        cookieSecret = getCookieSecret(certsDir)
        settings = {
            "cookie_secret": cookieSecret,
            "login_url": "/login",
            "xsrf_cookies": True,
            "websocket_max_message_size": 16*1024*1024,
            # "max_message_size": 1024*1024*256,
            # "max_buffer_size": 1024*1024*256,
        }
        Web.app = tornado.web.Application([
            (r'/', HttpHandler, dict(webObject=Web, page=Web.webIndexPage)),
            (r'/feedback', HttpHandler, dict(webObject=Web, page=Web.webBiofeedPage)),  # shows image
            (r'/login', LoginHandler, dict(webObject=Web)),
            (r'/logout', LogoutHandler, dict(webObject=Web)),
            (r'/wsUser', BaseWebSocketHandler, dict(name='wsUser', callback=Web.browserMainCallback)),
            (r'/wsSubject', BaseWebSocketHandler, dict(name='wsBioFeedback', callback=params.browserBiofeedCallback)),
            (r'/wsEvents', BaseWebSocketHandler, dict(name='wsEvent', callback=params.eventCallback)),  # gets signal to change image
            (r'/wsData', DataWebSocketHandler, dict(name='wsData', callback=Web.dataRequestHandler.callback)),
            (r'/src/(.*)', tornado.web.StaticFileHandler, {'path': src_root}),
            (r'/css/(.*)', tornado.web.StaticFileHandler, {'path': css_root}),
            (r'/img/(.*)', tornado.web.StaticFileHandler, {'path': img_root}),
            (r'/build/(.*)', tornado.web.StaticFileHandler, {'path': build_root}),
        ], **settings)
        # start event loop if needed
        try:
            asyncio.get_event_loop()
        except RuntimeError as err:
            # RuntimeError thrown if no current event loop
            # Start the event loop
            asyncio.set_event_loop(asyncio.new_event_loop())

        # start thread listening for remote file requests on a default named pipe
        commPipes = makeFifo(pipename=defaultPipeName)
        fifoThread = threading.Thread(name='defaultPipeThread', target=repeatPipeRequestHandler, args=(commPipes,))
        fifoThread.setDaemon(True)
        fifoThread.start()

        if Web.testMode is True:
            print("Listening on: http://localhost:{}".format(Web.httpPort))
            ssl_ctx = None
        else:
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(getCertPath(certsDir, sslCertFile),
                                    getKeyPath(certsDir, sslPrivateKey))
            print("Listening on: https://localhost:{}".format(Web.httpPort))

        Web.httpServer = tornado.httpserver.HTTPServer(Web.app, ssl_options=ssl_ctx)
        Web.httpServer.listen(Web.httpPort)
        Web.ioLoopInst = tornado.ioloop.IOLoop.current()
        Web.ioLoopInst.start()

    @staticmethod
    def stop():
        Web.ioLoopInst.add_callback(Web.ioLoopInst.stop)
        Web.app = None

    @staticmethod
    def close():
        # Currently this should never be called
        raise StateError("Web close() called")
        closeAllConnections()

    @staticmethod
    def dataLog(filename, logStr):
        cmd = {'cmd': 'dataLog', 'logLine': logStr, 'filename': filename}
        try:
            response = Web.wsDataRequest(cmd, timeout=5)
            if response.get('status') != 200:
                logging.warning('Web: dataLog: error {}'.format(response.get('error')))
                return False
        except Exception as err:
            logging.warning('Web: dataLog: error {}'.format(err))
            return False
        return True

    @staticmethod
    def userLog(logStr):
        cmd = {'cmd': 'userLog', 'value': logStr}
        Web.wsUserSendMsg(json.dumps(cmd))

    @staticmethod
    def sessionLog(logStr):
        cmd = {'cmd': 'sessionLog', 'value': logStr}
        Web.wsUserSendMsg(json.dumps(cmd))

    @staticmethod
    def setUserError(errStr):
        response = {'cmd': 'error', 'error': errStr}
        Web.wsUserSendMsg(json.dumps(response))

    @staticmethod
    def sendUserConfig(config, filename=''):
        response = {'cmd': 'config', 'value': config, 'filename': filename}
        Web.wsUserSendMsg(json.dumps(response))

    @staticmethod
    def sendUserDataVals(dataPoints):
        response = {'cmd': 'dataPoints', 'value': dataPoints}
        Web.wsUserSendMsg(json.dumps(response))

    @staticmethod
    def wsDataRequest(msg, timeout=None):
        call_id, conn = Web.dataRequestHandler.prepare_request(msg)
        cmd = msg.get('cmd')
        print(f'wsDataRequest, {cmd}, call_id {call_id}')
        Web.ioLoopInst.add_callback(sendWebSocketMessage, wsName='wsData', msg=json.dumps(msg), conn=conn)
        response = Web.dataRequestHandler.get_response(call_id, timeout=timeout)
        return response

    @staticmethod
    def wsUserSendMsg(msg):
        Web.ioLoopInst.add_callback(sendWebSocketMessage, wsName='wsUser', msg=msg)

    @staticmethod
    def wsBioFeedbackSendMsg(msg):
        Web.ioLoopInst.add_callback(sendWebSocketMessage, wsName='wsBioFeedback', msg=msg)

    @staticmethod
    def addResultValue(request):
        cmd = request.get('cmd')
        if cmd != 'resultValue':
            logging.warn('addResultValue: wrong cmd type {}'.format(cmd))
            return
        runId = request.get('runId')
        x = request.get('trId')
        y = request.get('value')
        if not isinstance(runId, numbers.Number) or runId <= 0:
            logging.warn('addResultValue: runId wrong val {}'.format(cmd))
            return
        # Make sure resultVals has at least as many arrays as runIds
        for i in range(len(Web.resultVals), runId):
            Web.resultVals.append([])
        if not isinstance(x, numbers.Number):
            # clear plot for this runId
            Web.resultVals[runId-1] = []
            return
        # logging.info("Add resultVal {}, {}".format(x, y))
        runVals = Web.resultVals[runId-1]
        for i, val in enumerate(runVals):
            if val['x'] == x:
                runVals[i] = {'x': x, 'y': y}
                return
        runVals.append({'x': x, 'y': y})


def getCookieSecret(dir):
    filename = os.path.join(dir, 'cookie-secret')
    if os.path.exists(filename):
        with open(filename, mode='rb') as fh:
            cookieSecret = fh.read()
    else:
        cookieSecret = uuid.uuid4().bytes
        with open(filename, mode='wb') as fh:
            fh.write(cookieSecret)
    return cookieSecret


#####################
# Callback Functions
#####################

def defaultBrowserMainCallback(client, message):
    request = json.loads(message)
    print(f'browserCallback: {request}')
    if 'config' in request:
        # Common code for any command that sends config information - retrieve the config info
        cfgData = request['config']
        newCfg = recurseCreateStructDict(cfgData)
        if newCfg is not None:
            Web.cfg = newCfg
        else:
            if cfgData is None:
                errStr = 'browserMainCallback: Config field is None'
            elif type(cfgData) not in (dict, list):
                errStr = 'browserMainCallback: Config field wrong type {}'.format(type(cfgData))
            else:
                errStr = 'browserMainCallback: Error parsing config field {}'.format(cfgData)
            Web.setUserError(errStr)
            return

    cmd = request['cmd']
    logging.log(DebugLevels.L3, "WEB USER CMD: %s", cmd)
    if cmd == "getDefaultConfig":
        # TODO - may need to remove certain fields that can't be jsonified
        if Web.configFilename is not None and Web.configFilename != '':
            cfg = loadConfigFile(Web.configFilename)
        else:
            cfg = Web.cfg
        Web.sendUserConfig(cfg, filename=Web.configFilename)
    elif cmd == "getDataPoints":
        Web.sendUserDataVals(Web.resultVals)
    elif cmd == "clearDataPoints":
        Web.resultVals = [[{'x': 0, 'y': 0}]]
    elif cmd == "run" or cmd == "initSession" or cmd == "finalizeSession":
        if Web.runInfo.threadId is not None:
            Web.runInfo.threadId.join(timeout=1)
            if Web.runInfo.threadId.is_alive():
                Web.setUserError("Client thread already runnning, skipping new request")
                return
            Web.runInfo.threadId = None
        Web.runInfo.stopRun = False
        if cmd == 'run':
            sessionScript = Web.fmriPyScript
            tag = 'running'
            logType = 'run'
        elif cmd == 'initSession':
            sessionScript = Web.initScript
            tag = 'initializing'
            logType = 'prep'
        elif cmd == "finalizeSession":
            sessionScript = Web.finalizeScript
            tag = 'finalizing'
            logType = 'prep'
        if sessionScript is None or sessionScript == '':
            Web.setUserError("{} script not set".format(cmd))
            return
        Web.runInfo.threadId = threading.Thread(name='sessionThread', target=runSession,
                                                args=(Web.cfg, sessionScript,
                                                      Web.filesremote, tag, logType))
        Web.runInfo.threadId.setDaemon(True)
        Web.runInfo.threadId.start()
    elif cmd == "stop":
        if Web.runInfo.threadId is not None:
            Web.runInfo.stopRun = True
            Web.runInfo.threadId.join(timeout=1)
            if not Web.runInfo.threadId.is_alive():
                Web.runInfo.threadId = None
                Web.runInfo.stopRun = False
    elif cmd == "uploadFiles":
        if Web.runInfo.uploadThread is not None:
            Web.runInfo.uploadThread.join(timeout=1)
            if Web.runInfo.uploadThread.is_alive():
                Web.setUserError("Upload thread already runnning, skipping new request")
                return
        Web.runInfo.uploadThread = threading.Thread(name='uploadFiles',
                                                    target=uploadFiles,
                                                    args=(request,))
        Web.runInfo.uploadThread.setDaemon(True)
        Web.runInfo.uploadThread.start()
    else:
        Web.setUserError("unknown command " + cmd)


def runSession(cfg, pyScript, filesremote, tag, logType='run'):
    # write out config file for use by pyScript
    if logType == 'run':
        configFileName = os.path.join(Web.confDir, 'cfg_sub{}_day{}_run{}.toml'.
                                      format(cfg.subjectName, cfg.subjectDay, cfg.runNum[0]))
    else:
        configFileName = os.path.join(Web.confDir, 'cfg_sub{}_day{}_{}.toml'.
                                      format(cfg.subjectName, cfg.subjectDay, tag))
    with open(configFileName, 'w+') as fd:
        toml.dump(cfg, fd)

    # specify -u python option to disable buffering print commands
    cmdStr = 'python -u {} -c {}'.format(pyScript, configFileName)
    # set option for remote file requests
    if filesremote is True:
        cmdStr += ' -x'
    # Create a project commPipe even if using local files so we can send
    #  classification results to the subject feedback window
    commPipes = makeFifo()
    cmdStr += ' --commpipe {}'.format(commPipes.fifoname)
    # start thread listening for remote file requests on fifo queue
    fifoThread = threading.Thread(name='fifoThread', target=commPipeRequestHandler, args=(commPipes,))
    fifoThread.setDaemon(True)
    fifoThread.start()
    # print(cmdStr)
    cmd = shlex.split(cmdStr)
    proc = subprocess.Popen(cmd, cwd=rootDir, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
    # send running status to user web page
    response = {'cmd': 'runStatus', 'status': tag}
    Web.wsUserSendMsg(json.dumps(response))
    # start a separate thread to read the process output
    lineQueue = queue.Queue()
    outputThread = threading.Thread(target=procOutputReader, args=(proc, lineQueue))
    outputThread.setDaemon(True)
    outputThread.start()
    line = 'start'
    while(proc.poll() is None or line != ''):
        # subprocess poll returns None while subprocess is running
        if Web.runInfo.stopRun is True:
            # signal the process to exit by closing stdin
            proc.stdin.close()
        try:
            line = lineQueue.get(block=True, timeout=1)
        except queue.Empty:
            line = ''
        if line != '':
            if logType == 'run':
                Web.userLog(line)
            else:
                Web.sessionLog(line)
            logging.info(line.rstrip())
    # processing complete, set status
    endStatus = tag + ' complete \u2714'
    if Web.runInfo.stopRun is True:
        endStatus = 'stopped'
    response = {'cmd': 'runStatus', 'status': endStatus}
    Web.wsUserSendMsg(json.dumps(response))
    outputThread.join(timeout=1)
    if outputThread.is_alive():
        print("OutputThread failed to exit")
    # make sure fifo thread has exited
    if fifoThread is not None:
        signalFifoExit(fifoThread, commPipes)
    return


def procOutputReader(proc, lineQueue):
    for bline in iter(proc.stdout.readline, b''):
        line = bline.decode('utf-8')
        # check if line has error in it and print to console
        if re.search('error', line, re.IGNORECASE):
            print(line)
        # send to output queue
        lineQueue.put(line)
        if line == '':
            break


def repeatPipeRequestHandler(commPipes):
    while True:
        commPipeRequestHandler(commPipes)


def commPipeRequestHandler(commPipes):
    '''A thread routine that listens for requests from a process through a pair of named pipes.
    This allows another process to send project requests without directly integrating
    the projectInterface into the process.
    Listens on an fd_in pipe for requests and writes the results back on the fd_out pipe.
    '''
    commPipes.fd_out = open(commPipes.name_out, mode='w', buffering=1)
    commPipes.fd_in = open(commPipes.name_in, mode='r')
    try:
        while True:
            msg = commPipes.fd_in.readline()
            if len(msg) == 0:
                # fifo closed
                break
            # parse command
            cmd = json.loads(msg)
            response = processPyScriptRequest(cmd)
            try:
                commPipes.fd_out.write(json.dumps(response) + os.linesep)
            except BrokenPipeError:
                print('handleFifoRequests: pipe broken')
                break
        # End while loop
    finally:
        logging.info('handleFifo thread exit')
        commPipes.fd_in.close()
        commPipes.fd_out.close()


def processPyScriptRequest(request):
    if 'cmd' not in request:
        raise StateError('handleFifoRequests: cmd field not in request: {}'.format(request))
    cmd = request['cmd']
    route = request.get('route')
    localtimeout = request.get('timeout', 10) + 5
    response = StructDict({'status': 200})
    if route == 'dataserver':
        try:
            response = Web.wsDataRequest(request, timeout=localtimeout)
            if response is None:
                raise StateError('handleFifoRequests: Response None from sendDataMessage')
            if 'status' not in response:
                raise StateError('handleFifoRequests: status field missing from response: {}'.format(response))
            if response['status'] not in (200, 408):
                if 'error' not in response:
                    raise StateError('handleFifoRequests: error field missing from response: {}'.format(response))
                Web.setUserError(response['error'])
                logging.error('handleFifo status {}: {}'.format(response['status'], response['error']))
        except Exception as err:
            errStr = 'SendDataMessage Exception type {}: error {}:'.format(type(err), str(err))
            response = {'status': 400, 'error': errStr}
            Web.setUserError(errStr)
            logging.error('handleFifo Excpetion: {}'.format(errStr))
            raise err
    else:
        if cmd == 'webCommonDir':
            response.filename = CommonOutputDir
        elif cmd == 'resultValue':
            try:
                # forward to bioFeedback Display
                Web.wsBioFeedbackSendMsg(json.dumps(request))
                # forward to main browser window
                Web.wsUserSendMsg(json.dumps(request))
                # Accumulate results locally to resend to browser as needed
                Web.addResultValue(request)
            except Exception as err:
                errStr = 'SendClassification Exception type {}: error {}:'.format(type(err), str(err))
                response = {'status': 400, 'error': errStr}
                Web.setUserError(errStr)
                logging.error('handleFifo Excpetion: {}'.format(errStr))
                raise err
        elif cmd == 'subjectDisplay':
            logging.info('subjectDisplay projectInterface Callback')
    return response


def signalFifoExit(fifoThread, commPipes):
    '''Under normal exit conditions the fifothread will exit when the fifo filehandles
    are closed. However if the fifo filehandles were never opened by both ends then
    the fifothread can be blocked waiting for them to open. To handle that case
    we open both filehandles with O_NONBLOCK flag so that if the fifo thread reader
    is listening it will be opened and closed, if not it will throw OSError exception
    in which case the fifothread has already exited and closed the fifo filehandles.
    '''
    if fifoThread is None:
        return
    try:
        pipeout = os.open(commPipes.name_out, os.O_RDONLY | os.O_NONBLOCK)
        os.close(pipeout)
        # trigger context swap to allow handleFifoRequests to open next pipe if needed
        time.sleep(0.1)
        pipein = os.open(commPipes.name_in, os.O_WRONLY | os.O_NONBLOCK)
        os.close(pipein)
    except OSError as err:
        # No reader/writer listening on file so fifoThread already exited
        # print('signalFifoExit: exception {}'.format(err))
        pass
    fifoThread.join(timeout=1)
    if fifoThread.is_alive() is not False:
        raise StateError('runSession: fifoThread not completed')


def handleDataRequest(cmd):
    savedError = None
    incomplete = True
    while incomplete:
        response = Web.wsDataRequest(cmd, timeout=60)
        if response.get('status') != 200:
            raise RequestError('handleDataRequest: status not 200: {}'.format(response.get('status')))
        try:
            data = unpackDataMessage(response)
        except Exception as err:
            logging.error('handleDataRequest: unpackDataMessage: {}'.format(err))
            if savedError is None:
                savedError = err
        cmd['callId'] = response.get('callId', -1)
        incomplete = response.get('incomplete', False)
    if savedError:
        raise RequestError('handleDataRequest: unpackDataMessage: {}'.format(savedError))
    return data


def uploadFiles(request):
    if 'cmd' not in request or request['cmd'] != "uploadFiles":
        raise StateError('uploadFiles: incorrect cmd request: {}'.format(request))
    try:
        srcFile = request['srcFile']
        compress = request['compress']
    except KeyError as err:
        Web.setUserError("UploadFiles request missing a parameter: {}".format(err))
        return
    # get the list of file to upload
    cmd = listFilesReqStruct(srcFile)
    # TODO - add a try catch for this request in case the fileWatcher isn't connected?
    response = Web.wsDataRequest(cmd, timeout=10)
    if response.get('status') != 200:
        Web.setUserError("Error listing files {}: {}".
                         format(srcFile, response.get('error')))
        return
    fileList = response.get('fileList')
    if type(fileList) is not list:
        Web.setUserError("Invalid fileList reponse type {}: expecting list".
                         format(type(fileList)))
        return
    if len(fileList) == 0:
        response = {'cmd': 'uploadProgress', 'file': 'No Matching Files'}
        Web.wsUserSendMsg(json.dumps(response))
        return
    for file in fileList:
        try:
            cmd = getFileReqStruct(file, compress=compress)
            data = handleDataRequest(cmd)
            # write the returned data out to a file
            filename = response.get('filename')
            if filename is None:
                if 'data' in response: del response['data']
                raise StateError('sendDataRequestToFile: filename field not in response: {}'.format(response))
            # prepend with common output path and write out file
            # note: can't just use os.path.join() because if two or more elements
            #   have an aboslute path it discards the earlier elements
            global CommonOutputDir
            outputFilename = os.path.normpath(CommonOutputDir + filename)
            dirName = os.path.dirname(outputFilename)
            if not os.path.exists(dirName):
                os.makedirs(dirName)
            writeFile(outputFilename, data)
            response['filename'] = outputFilename
        except Exception as err:
            Web.setUserError(
                "Error uploading file {}: {}".format(file, str(err)))
            return
        response = {'cmd': 'uploadProgress', 'file': file}
        Web.wsUserSendMsg(json.dumps(response))
    response = {'cmd': 'uploadProgress', 'file': '------upload complete------'}
    Web.wsUserSendMsg(json.dumps(response))
