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
import asyncio
import threading
import subprocess
from pathlib import Path
from base64 import b64decode
from rtCommon.structDict import StructDict, recurseCreateStructDict
from rtCommon.certsUtils import getCertPath, getKeyPath
from rtCommon.utils import DebugLevels, writeFile
from rtCommon.errors import StateError, RTError

certsDir = 'certs'
sslCertFile = 'rtcloud.crt'
sslPrivateKey = 'rtcloud_private.key'
CommonOutputDir = '/rtfmriData/'
maxDaysLoginCookieValid = 0.5

moduleDir = os.path.dirname(os.path.realpath(__file__))
rootDir = os.path.dirname(moduleDir)
confDir = os.path.join(moduleDir, 'conf/')
if not os.path.exists(confDir):
    os.makedirs(confDir)

# Note: User refers to the clinician running the experiment, so userWindow is the main
#  browser window for running the experiment.


class Web():
    ''' Cloud service web-interface that is the front-end to the data processing. '''
    app = None
    httpServer = None
    httpPort = 8888
    # Arrays of WebSocket connections that have been established from client windows
    wsBrowserMainConns = []  # type: ignore
    wsBiofeedbackConns = []  # type: ignore
    wsEventConns = []  # type: ignore
    wsDataConn = None  # type: ignore  # Only one data connection
    # Callback functions to invoke when message received from client window connection
    browserMainCallback = None
    browserBiofeedCallback = None
    eventCallback = None
    # Main html page to load
    webDir = moduleDir
    htmlDir = os.path.join(webDir, 'html')
    webIndexPage = 'index.html'
    webLoginPage = 'login.html'
    webBiofeedPage = 'biofeedback.html'
    dataCallbacks = {}
    dataSequenceNum = 0
    cbPruneTime = 0
    # Synchronizing across threads
    threadLock = threading.Lock()
    ioLoopInst = None
    filesremote = False
    fmriPyScript = None
    cfg = None
    test = False
    runInfo = StructDict({'threadId': None, 'stopRun': False})

    @staticmethod
    def start(params, cfg, test=False):
        if Web.app is not None:
            raise RuntimeError("Web Server already running.")
        Web.test = test
        # Set default value before checking for param overrides
        Web.browserMainCallback = defaultBrowserMainCallback
        Web.browserBiofeedCallback = defaultBrowserBiofeedCallback
        Web.eventCallback = defaultEventCallback
        if params.browserMainCallback:
            Web.browserMainCallback = params.browserMainCallback
        if params.browserBiofeedCallback:
            Web.browserBiofeedCallback = params.browserBiofeedCallback
        if params.eventCallback:
            Web.eventCallback = params.eventCallback
        if params.htmlDir:
            Web.htmlDir = params.htmlDir
            Web.webDir = os.path.dirname(Web.htmlDir)
        if params.port:
            Web.httpPort = params.port
        Web.fmriPyScript = params.fmriPyScript
        Web.filesremote = params.filesremote
        Web.cfg = cfg
        src_root = os.path.join(Web.webDir, 'src')
        css_root = os.path.join(Web.webDir, 'css')
        img_root = os.path.join(Web.webDir, 'img')
        build_root = os.path.join(Web.webDir, 'build')
        cookieSecret = getCookieSecret(certsDir)
        settings = {
            "cookie_secret": cookieSecret,
            "login_url": "/login",
            "xsrf_cookies": True,
        }
        Web.app = tornado.web.Application([
            (r'/', Web.UserHttp),
            (r'/login', Web.LoginHandler),
            (r'/logout', Web.LogoutHandler),
            (r'/feedback', Web.BiofeedbackHttp),  # shows image
            (r'/wsUser', Web.UserWebSocket),
            (r'/wsSubject', Web.BiofeedbackWebSocket),
            (r'/wsData', Web.DataWebSocket),
            (r'/wsEvents', Web.EventWebSocket),  # gets signal to change image
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

        Web.threadLock.acquire()
        try:
            if Web.wsDataConn is not None:
                Web.wsDataConn.close()
            Web.wsDataConn = None

            for client in Web.wsBrowserMainConns[:]:
                client.close()
            Web.wsBrowserMainConns = []

            for client in Web.wsBiofeedbackConns[:]:
                client.close()
            Web.wsBiofeedbackConns = []
        finally:
            Web.threadLock.release()

    @staticmethod
    def dataLog(filename, logStr):
        cmd = {'cmd': 'dataLog', 'logLine': logStr, 'filename': filename}
        try:
            Web.sendDataMsgFromThread(cmd, timeout=5)
        except Exception as err:
            logging.warning('Web: dataLog: error {}'.format(err))
            return False
        return True

    @staticmethod
    def userLog(logStr):
        cmd = {'cmd': 'userLog', 'value': logStr}
        Web.sendUserMsgFromThread(json.dumps(cmd))

    @staticmethod
    def setUserError(errStr):
        response = {'cmd': 'error', 'error': errStr}
        Web.sendUserMsgFromThread(json.dumps(response))

    @staticmethod
    def sendUserConfig(config, filesremote=True):
        response = {'cmd': 'config', 'value': config, 'filesremote': filesremote}
        Web.sendUserMsgFromThread(json.dumps(response))

    @staticmethod
    def sendDataMessage(cmd, callbackStruct):
        if callbackStruct is None or callbackStruct.event is None:
            raise StateError("sendDataMessage: No threading.event attribute in callbackStruct")
        Web.threadLock.acquire()
        try:
            Web.dataSequenceNum += 1
            seqNum = Web.dataSequenceNum
            cmd['seqNum'] = seqNum
            msg = json.dumps(cmd)
            callbackStruct.seqNum = seqNum
            callbackStruct.timeStamp = time.time()
            callbackStruct.status = 0
            callbackStruct.error = None
            Web.dataCallbacks[seqNum] = callbackStruct
            Web.wsDataConn.write_message(msg)
        except Exception as err:
            errStr = 'sendDataMessage error: type {}: {}'.format(type(err), str(err))
            raise RTError(errStr)
        finally:
            Web.threadLock.release()

    @staticmethod
    def dataCallback(client, message):
        response = json.loads(message)
        if 'cmd' not in response:
            raise StateError('dataCallback: cmd field missing from response: {}'.format(response))
        if 'status' not in response:
            raise StateError('dataCallback: status field missing from response: {}'.format(response))
        if 'seqNum' not in response:
            raise StateError('dataCallback: seqNum field missing from response: {}'.format(response))
        seqNum = response['seqNum']
        origCmd = response['cmd']
        logging.log(DebugLevels.L6, "callback {}: {} {}".format(seqNum, origCmd, response['status']))
        # Thread Synchronized Section
        Web.threadLock.acquire()
        try:
            callbackStruct = Web.dataCallbacks.pop(seqNum, None)
            if callbackStruct is None:
                logging.error('WebServer: dataCallback seqNum {} not found, current seqNum {}'
                              .format(seqNum, Web.dataSequenceNum))
                return
            if callbackStruct.seqNum != seqNum:
                # This should never happen
                raise StateError('seqNum mismtach {} {}'.format(callbackStruct.seqNum, seqNum))
            callbackStruct.response = response
            callbackStruct.status = response['status']
            if callbackStruct.status == 200:
                if origCmd in ('ping', 'initWatch', 'putTextFile', 'dataLog'):
                    pass
                elif origCmd in ('getFile', 'getNewestFile', 'watchFile'):
                    if 'data' not in response:
                        raise StateError('dataCallback: data field missing from response: {}'.format(response))
                else:
                    callbackStruct.error = 'Unrecognized origCmd {}'.format(origCmd)
            else:
                if 'error' not in response or response['error'] == '':
                    raise StateError('dataCallback: error field missing from response: {}'.format(response))
                callbackStruct.error = response['error']
            callbackStruct.event.set()
        except Exception as err:
            logging.error('WebServer: dataCallback error: {}'.format(err))
            raise err
        finally:
            Web.threadLock.release()
        if time.time() > Web.cbPruneTime:
            Web.cbPruneTime = time.time() + 60
            Web.pruneCallbacks()

    @staticmethod
    def pruneCallbacks():
        numWaitingCallbacks = len(Web.dataCallbacks)
        if numWaitingCallbacks == 0:
            return
        logging.info('Web pruneCallbacks: checking {} callbaks'.format(numWaitingCallbacks))
        Web.threadLock.acquire()
        try:
            maxSeconds = 300
            now = time.time()
            for seqNum in Web.dataCallbacks.keys():
                # check how many seconds old each callback is
                cb = Web.dataCallbacks[seqNum]
                secondsElapsed = now - cb.timeStamp
                if secondsElapsed > maxSeconds:
                    # older than max threshold so remove
                    cb.status = 400
                    cb.error = 'Callback time exceeded max threshold {}s {}s'.format(maxSeconds, secondsElapsed)
                    cb.response = {'cmd': 'unknown', 'status': cb.status, 'error': cb.error}
                    cb.event.set()
                    del Web.dataCallbacks[seqNum]
        except Exception as err:
            logging.error('Web pruneCallbacks: error {}'.format(err))
        finally:
            Web.threadLock.release()

    @staticmethod
    def sendUserMessage(msg):
        Web.threadLock.acquire()
        try:
            for client in Web.wsBrowserMainConns:
                client.write_message(msg)
        finally:
            Web.threadLock.release()

    @staticmethod
    def sendBiofeedbackMessage(msg):
        Web.threadLock.acquire()
        try:
            for client in Web.wsBiofeedbackConns:
                client.write_message(msg)
        finally:
            Web.threadLock.release()

    @staticmethod
    def sendDataMsgFromThread(msg, timeout=None):
        if Web.wsDataConn is None:
            raise StateError("WebServer: No Data Websocket Connection")
        callbackStruct = StructDict()
        callbackStruct.event = threading.Event()
        # schedule the call with io thread
        Web.ioLoopInst.add_callback(Web.sendDataMessage, msg, callbackStruct)
        # wait for completion of call
        callbackStruct.event.wait(timeout)
        if callbackStruct.event.is_set() is False:
            raise TimeoutError("sendDataMessage: Data Request Timed Out({}) {}".format(timeout, msg))
        if callbackStruct.response is None:
            raise StateError('sendDataMessage: callbackStruct.response is None for command {}'.format(msg))
        if callbackStruct.status == 200 and 'writefile' in callbackStruct.response:
            writeResponseDataToFile(callbackStruct.response)
        return callbackStruct.response

    @staticmethod
    def sendUserMsgFromThread(msg):
        Web.ioLoopInst.add_callback(Web.sendUserMessage, msg)

    @staticmethod
    def sendBiofeedbackMsgFromThread(msg):
        Web.ioLoopInst.add_callback(Web.sendBiofeedbackMessage, msg)

    class UserHttp(tornado.web.RequestHandler):
        def get_current_user(self):
            return self.get_secure_cookie("login", max_age_days=maxDaysLoginCookieValid)

        @tornado.web.authenticated
        def get(self):
            full_path = os.path.join(Web.htmlDir, Web.webIndexPage)
            logging.log(DebugLevels.L6, 'Index request: pwd: {}'.format(full_path))
            Web.threadLock.acquire()
            try:
                self.render(full_path)
            finally:
                Web.threadLock.release()

    class BiofeedbackHttp(tornado.web.RequestHandler):
        def get_current_user(self):
            return self.get_secure_cookie("login", max_age_days=maxDaysLoginCookieValid)

        @tornado.web.authenticated
        def get(self):
            full_path = os.path.join(Web.htmlDir, Web.webBiofeedPage)
            logging.log(DebugLevels.L6, 'Subject feedback http request: pwd: {}'.format(full_path))
            Web.threadLock.acquire()
            try:
                self.render(full_path)
            finally:
                Web.threadLock.release()

    class LoginHandler(tornado.web.RequestHandler):
        loginAttempts = {}
        loginRetryDelay = 10

        def get(self):
            params = {
                "error_msg": '',
                "nextpage": self.get_argument("next", "/")
            }
            full_path = os.path.join(Web.htmlDir, Web.webLoginPage)
            self.render(full_path,  **params)

        def post(self):
            errorReply = None
            try:
                login_name = self.get_argument("name")
                login_passwd = self.get_argument("password")
                if Web.test is True:
                    if login_name == login_passwd == 'test':
                        self.set_secure_cookie("login", login_name, expires_days=maxDaysLoginCookieValid)
                        self.redirect(self.get_query_argument('next', '/'))
                        return
                passwdFilename = os.path.join(certsDir, 'passwd')
                passwdDict = loadPasswdFile(passwdFilename)
                if login_name in passwdDict:
                    errorReply = self.checkRetry(login_name)
                    if errorReply is None:
                        hashed_passwd = passwdDict[login_name]
                        # checkpw expects bytes array rather than string so use .encode()
                        if bcrypt.checkpw(login_passwd.encode(), hashed_passwd.encode()) is True:
                            # Remove failed attempts entry
                            del Web.LoginHandler.loginAttempts[login_name]
                            self.set_secure_cookie("login", login_name, expires_days=maxDaysLoginCookieValid)
                            self.redirect(self.get_query_argument('next', '/'))
                            return
                        else:
                            errorReply = 'Login Error: Login Incorrect'
                else:
                    errorReply = self.checkRetry('invalid_user')
                    if errorReply is None:
                        errorReply = 'Login Error: Login Incorrect'
            except Exception as err:
                errorReply = 'Exception: {} {}'.format(type(err), err)
            assert errorReply is not None, "Assert: Web.LoginHandler.error not empty"
            logging.warning('Login Failure: {}'.format(login_name))
            params = {
                "error_msg": errorReply,
                "nextpage": self.get_query_argument('next', '/')
            }
            full_path = os.path.join(Web.htmlDir, Web.webLoginPage)
            self.render(full_path,  **params)

        def checkRetry(self, user):
            '''Keep a dictionary with one entry per username. Any user not in the
                passwd file will be entered as 'invalid_user'. Record login failure
                count and timestamp for when the next retry is allowed. Reset failed
                retry count on successful login. Return message with how many seconds
                until next login attempt is allowed.
            '''
            now = time.time()
            loginAttempts = Web.LoginHandler.loginAttempts
            retryTime = now + Web.LoginHandler.loginRetryDelay
            loginTry = loginAttempts.get(user)
            if loginTry is not None:
                failedLogins = loginTry.get('failedLogins', 0)
                nextAllowedTime = loginTry.get('nextAllowedTime', now)
                # print('user: {}, tries {}, nextTime {}'.format(user, failedLogins, nextAllowedTime))
                if nextAllowedTime > now:
                    delaySecs = loginTry['nextAllowedTime'] - now
                    return 'Next login retry allowed in {} sec'.format(int(delaySecs))
                loginTry['failedLogins'] = failedLogins + 1
                loginTry['nextAllowedTime'] = retryTime
                loginAttempts[user] = loginTry
            else:
                loginAttempts[user] = {'failedLogins': 1, 'nextAllowedTime': retryTime}
            return None

    class LogoutHandler(tornado.web.RequestHandler):
        def get(self):
            self.clear_cookie("login")
            self.redirect("/login")

    class BiofeedbackWebSocket(tornado.websocket.WebSocketHandler):
        # TODO - combine these in-common setups into helper functions
        def open(self):
            user_id = self.get_secure_cookie("login")
            if not user_id:
                response = {'cmd': 'error', 'error': 'Websocket authentication failed'}
                self.write_message(json.dumps(response))
                self.close()
                return
            logging.log(DebugLevels.L1, "Biofeedback WebSocket opened")
            Web.threadLock.acquire()
            try:
                Web.wsBiofeedbackConns.append(self)
            finally:
                Web.threadLock.release()

        def on_close(self):
            logging.log(DebugLevels.L1, "Biofeedback WebSocket closed")
            Web.threadLock.acquire()
            try:
                if self in Web.wsBiofeedbackConns:
                    Web.wsBiofeedbackConns.remove(self)
            finally:
                Web.threadLock.release()

        def on_message(self, message):
            Web.browserBiofeedCallback(self, message)

    class UserWebSocket(tornado.websocket.WebSocketHandler):
        # def get(self, *args, **kwargs):
        #     if self.get_secure_cookie("login"):
        #         super(Web.BiofeedbackWebSocket, self).get(*args, **kwargs)
        #     else:
        #         What to do here when authentication fails?
        #         return

        def open(self):
            user_id = self.get_secure_cookie("login")
            if not user_id:
                response = {'cmd': 'error', 'error': 'Websocket authentication failed'}
                self.write_message(json.dumps(response))
                self.close()
                return
            logging.log(DebugLevels.L1, "User WebSocket opened")
            Web.threadLock.acquire()
            try:
                Web.wsBrowserMainConns.append(self)
            finally:
                Web.threadLock.release()

        def on_close(self):
            logging.log(DebugLevels.L1, "User WebSocket closed")
            Web.threadLock.acquire()
            try:
                if self in Web.wsBrowserMainConns:
                    Web.wsBrowserMainConns.remove(self)
                else:
                    logging.log(DebugLevels.L1, "on_close: connection not in list")
            finally:
                Web.threadLock.release()

        def on_message(self, message):
            Web.browserMainCallback(self, message)

    class EventWebSocket(tornado.websocket.WebSocketHandler):
        def open(self):
            user_id = self.get_secure_cookie("login")
            if not user_id:
                response = {'cmd': 'error', 'error': 'Websocket authentication failed'}
                self.write_message(json.dumps(response))
                self.close()
                return
            logging.log(DebugLevels.L1, "Event WebSocket opened")
            Web.threadLock.acquire()
            try:
                Web.wsEventConns.append(self)
            finally:
                Web.threadLock.release()

        def on_close(self):
            logging.log(DebugLevels.L1, "Event WebSocket closed")
            Web.threadLock.acquire()
            try:
                if self in Web.wsEventConns:
                    Web.wsEventConns.remove(self)
            finally:
                Web.threadLock.release()

        def on_message(self, message):
            Web.eventCallback(self, message)

    class DataWebSocket(tornado.websocket.WebSocketHandler):
        def open(self):
            user_id = self.get_secure_cookie("login")
            if not user_id:
                logging.warning('Data websocket authentication failed')
                response = {'cmd': 'error', 'status': 401, 'error': 'Websocket authentication failed'}
                self.write_message(json.dumps(response))
                self.close()
                return
            logging.log(DebugLevels.L1, "Data WebSocket opened")
            Web.threadLock.acquire()
            try:
                # close any existing connections
                if Web.wsDataConn is not None:
                    Web.wsDataConn.close()
                # add new connection
                Web.wsDataConn = self
                print('DataWebSocket: connected {}'.format(self.request.remote_ip))
            except Exception as err:
                logging.error('WebServer: Open Data Socket error: {}'.format(err))
            finally:
                Web.threadLock.release()

        def on_close(self):
            if Web.wsDataConn != self:
                logging.log(DebugLevels.L1, "on_close: Data Socket mismatch")
                return
            logging.log(DebugLevels.L1, "Data WebSocket closed")
            Web.threadLock.acquire()
            try:
                Web.wsDataConn = None
                # signal the close to anyone waiting for replies
                for seqNum, cb in Web.dataCallbacks.items():
                    cb.status = 499
                    cb.error = 'Client closed connection'
                    cb.response = {'cmd': 'unknown', 'status': cb.status, 'error': cb.error}
                    cb.event.set()
                Web.dataCallbacks = {}
            finally:
                Web.threadLock.release()

        def on_message(self, message):
            Web.dataCallback(self, message)


def loadPasswdFile(filename):
    with open(filename, 'r') as fh:
        entries = fh.readlines()
    passwdDict = {k: v for (k, v) in [line.strip().split(',') for line in entries]}
    return passwdDict


def storePasswdFile(filename, passwdDict):
    with open(filename, 'w') as fh:
        for k, v in passwdDict.items():
            fh.write('{},{}\n'.format(k, v))


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


def writeResponseDataToFile(response):
    '''For responses that have writefile set, write the data to a file'''
    global CommonOutputDir
    if response['status'] != 200:
        raise StateError('writeResponseDataToFile: status not 200')
    if 'writefile' in response and response['writefile'] is True:
        # write the returned data out to a file
        if 'data' not in response:
            raise StateError('writeResponseDataToFile: data field not in response: {}'.format(response))
        if 'filename' not in response:
            del response['data']
            raise StateError('writeResponseDataToFile: filename field not in response: {}'.format(response))
        filename = response['filename']
        decodedData = b64decode(response['data'])
        # prepend with common output path and write out file
        # note: can't just use os.path.join() because if two or more elements
        #   have an aboslute path it discards the earlier elements
        outputFilename = os.path.normpath(CommonOutputDir + filename)
        dirName = os.path.dirname(outputFilename)
        if not os.path.exists(dirName):
            os.makedirs(dirName)
        writeFile(outputFilename, decodedData)
        response['filename'] = outputFilename
        del response['data']


#####################
# Callback Functions
#####################

def defaultBrowserMainCallback(client, message):
    request = json.loads(message)
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
        Web.sendUserConfig(Web.cfg, filesremote=Web.filesremote)
    elif cmd == "run":
        if Web.runInfo.threadId is not None:
            Web.runInfo.threadId.join(timeout=1)
            if Web.runInfo.threadId.is_alive():
                Web.setUserError("Client thread already runnning, skipping new request")
                return
            Web.runInfo.threadId = None
        Web.runInfo.stopRun = False
        Web.runInfo.threadId = threading.Thread(name='runSessionThread', target=runSession,
                                                args=(Web.cfg, Web.fmriPyScript, Web.filesremote))
        Web.runInfo.threadId.setDaemon(True)
        Web.runInfo.threadId.start()
    elif cmd == "stop":
        if Web.runInfo.threadId is not None:
            Web.runInfo.stopRun = True
            Web.runInfo.threadId.join(timeout=1)
            if not Web.runInfo.threadId.is_alive():
                Web.runInfo.threadId = None
                Web.runInfo.stopRun = False
    else:
        Web.setUserError("unknown command " + cmd)


def defaultBrowserBiofeedCallback(client, message):
    request = json.loads(message)
    cmd = request['cmd']
    logging.log(DebugLevels.L3, "WEB SUBJ CMD: %s", cmd)
    print('Subject Callback: {}'.format(cmd))


def defaultEventCallback(client, message):
    request = json.loads(message)
    cmd = request['cmd']
    logging.log(DebugLevels.L3, "WEB EVENT CMD: %s", cmd)
    print('Event Callback: {}'.format(cmd))


def runSession(cfg, pyScript, filesremote=False):
    # write out config file for use by pyScript
    configFileName = os.path.join(confDir, 'cfg_{}_day{}_run{}.toml'.
                                  format(cfg.subjectName,
                                         cfg.subjectDay,
                                         cfg.Runs[0]))
    with open(configFileName, 'w+') as fd:
        toml.dump(cfg, fd)

    # specify -u python option to disable buffering print commands
    cmdStr = 'python -u {} -c {}'.format(pyScript, configFileName)
    # set option for remote file requests
    if filesremote is True:
        cmdStr += ' -x'
    # Create a webpipe session even if using local files so we can send
    #  classification results to the subject feedback window
    webpipes = makeFifo()
    cmdStr += ' --webpipe {}'.format(webpipes.fifoname)
    # start thread listening for remote file requests on fifo queue
    fifoThread = threading.Thread(name='fifoThread', target=pyScriptRequestHandler, args=(webpipes,))
    fifoThread.setDaemon(True)
    fifoThread.start()
    # print(cmdStr)
    cmd = shlex.split(cmdStr)
    proc = subprocess.Popen(cmd, cwd=rootDir, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
    # send running status to user web page
    response = {'cmd': 'runStatus', 'status': 'running'}
    Web.sendUserMsgFromThread(json.dumps(response))
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
            Web.userLog(line)
    # processing complete, set status
    endStatus = 'complete \u2714'
    if Web.runInfo.stopRun is True:
        endStatus = 'stopped'
    response = {'cmd': 'runStatus', 'status': endStatus}
    Web.sendUserMsgFromThread(json.dumps(response))
    outputThread.join(timeout=1)
    if outputThread.is_alive():
        print("OutputThread failed to exit")
    # make sure fifo thread has exited
    if fifoThread is not None:
        signalFifoExit(fifoThread, webpipes)
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


def pyScriptRequestHandler(webpipes):
    '''A thread routine that listens for requests from a process through a pair of named pipes.
    This allows another process to send web requests without directly integrating
    the web server into the process.
    Listens on an fd_in pipe for requests and writes the results back on the fd_out pipe.
    '''
    webpipes.fd_out = open(webpipes.name_out, mode='w', buffering=1)
    webpipes.fd_in = open(webpipes.name_in, mode='r')
    try:
        while True:
            msg = webpipes.fd_in.readline()
            if len(msg) == 0:
                # fifo closed
                break
            # parse command
            cmd = json.loads(msg)
            response = processPyScriptRequest(cmd)
            try:
                webpipes.fd_out.write(json.dumps(response) + os.linesep)
            except BrokenPipeError:
                print('handleFifoRequests: pipe broken')
                break
        # End while loop
    finally:
        logging.info('handleFifo thread exit')
        webpipes.fd_in.close()
        webpipes.fd_out.close()


def processPyScriptRequest(request):
    if 'cmd' not in request:
        raise StateError('handleFifoRequests: cmd field not in request: {}'.format(request))
    cmd = request['cmd']
    route = request.get('route')
    response = StructDict({'status': 200})
    if route == 'dataserver':
        try:
            response = Web.sendDataMsgFromThread(request, timeout=10)
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
        elif cmd == 'classificationResult':
            try:
                # forward to bioFeedback Display
                Web.sendBiofeedbackMsgFromThread(json.dumps(request))
                # forward to main browser window
                Web.sendUserMsgFromThread(json.dumps(request))
            except Exception as err:
                errStr = 'SendClassification Exception type {}: error {}:'.format(type(err), str(err))
                response = {'status': 400, 'error': errStr}
                Web.setUserError(errStr)
                logging.error('handleFifo Excpetion: {}'.format(errStr))
                raise err
        elif cmd == 'subjectDisplay':
            logging.info('subjectDisplay webServerCallback')
    return response


def signalFifoExit(fifoThread, webpipes):
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
        pipeout = os.open(webpipes.name_out, os.O_RDONLY | os.O_NONBLOCK)
        os.close(pipeout)
        # trigger context swap to allow handleFifoRequests to open next pipe if needed
        time.sleep(0.1)
        pipein = os.open(webpipes.name_in, os.O_WRONLY | os.O_NONBLOCK)
        os.close(pipein)
    except OSError as err:
        # No reader/writer listening on file so fifoThread already exited
        # print('signalFifoExit: exception {}'.format(err))
        pass
    fifoThread.join(timeout=1)
    if fifoThread.is_alive() is not False:
        raise StateError('runSession: fifoThread not completed')


def makeFifo():
    fifodir = '/tmp/pipes/'
    if not os.path.exists(fifodir):
        os.makedirs(fifodir)
    # remove all previous pipes
    for p in Path(fifodir).glob("web_*"):
        p.unlink()
    # create new pipe
    fifoname = os.path.join(fifodir, 'web_pipe_{}'.format(int(time.time())))
    # fifo stuct
    webpipes = StructDict()
    webpipes.name_out = fifoname + '.toclient'
    webpipes.name_in = fifoname + '.fromclient'
    if not os.path.exists(webpipes.name_out):
        os.mkfifo(webpipes.name_out)
    if not os.path.exists(webpipes.name_in):
        os.mkfifo(webpipes.name_in)
    webpipes.fifoname = fifoname
    return webpipes
