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

certsDir = 'certs'
sslCertFile = 'rtcloud.crt'
sslPrivateKey = 'rtcloud_private.key'
CommonOutputDir = '/rtfmriData/'
maxDaysLoginCookieValid = 0.5


moduleDir = os.path.dirname(os.path.realpath(__file__))
rootDir = os.path.dirname(moduleDir)

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
    webDir = os.path.join(rootDir, 'web/')
    confDir = os.path.join(webDir, 'conf/')
    htmlDir = os.path.join(webDir, 'html')
    webIndexPage = 'index.html'
    webLoginPage = 'login.html'
    webBiofeedPage = 'biofeedback.html'
    dataCallbacks = {}
    dataSequenceNum = 0
    cbPruneTime = 0
    # Synchronizing across threads
    callbackLock = threading.Lock()
    wsConnLock = threading.Lock()
    httpLock = threading.Lock()
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

    @staticmethod
    def start(params, cfg, testMode=False):
        if Web.app is not None:
            raise RuntimeError("Web Server already running.")
        Web.testMode = testMode
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

        Web.wsConnLock.acquire()
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
            Web.wsConnLock.release()

    @staticmethod
    def dataLog(filename, logStr):
        cmd = {'cmd': 'dataLog', 'logLine': logStr, 'filename': filename}
        try:
            response = Web.sendDataMsgFromThread(cmd, timeout=5)
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
        Web.sendUserMsgFromThread(json.dumps(cmd))

    @staticmethod
    def sessionLog(logStr):
        cmd = {'cmd': 'sessionLog', 'value': logStr}
        Web.sendUserMsgFromThread(json.dumps(cmd))

    @staticmethod
    def setUserError(errStr):
        response = {'cmd': 'error', 'error': errStr}
        Web.sendUserMsgFromThread(json.dumps(response))

    @staticmethod
    def sendUserConfig(config, filename=''):
        response = {'cmd': 'config', 'value': config, 'filename': filename}
        Web.sendUserMsgFromThread(json.dumps(response))

    @staticmethod
    def sendUserDataVals(dataPoints):
        response = {'cmd': 'dataPoints', 'value': dataPoints}
        Web.sendUserMsgFromThread(json.dumps(response))

    @staticmethod
    def sendDataMsgFromThreadAsync(msg):
        if Web.wsDataConn is None:
            raise StateError("ProjectInterface: FileServer not connected. Please run the fileServer.")
        callId = msg.get('callId')
        if not callId:
            callbackStruct = StructDict()
            callbackStruct.dataConn = Web.wsDataConn
            callbackStruct.numResponses = 0
            callbackStruct.responses = []
            callbackStruct.semaphore = threading.Semaphore(value=0)
            callbackStruct.timeStamp = time.time()
            callbackStruct.msg = msg.copy()
            if 'data' in callbackStruct.msg:
                del callbackStruct.msg['data']
            Web.callbackLock.acquire()
            try:
                Web.dataSequenceNum += 1
                callId = Web.dataSequenceNum
                callbackStruct.callId = callId
                msg['callId'] = callId
                Web.dataCallbacks[callId] = callbackStruct
            finally:
                Web.callbackLock.release()
            Web.ioLoopInst.add_callback(Web.sendDataMessage, msg)
        return callId

    @staticmethod
    def getDataMsgResponse(callId, timeout=None):
        Web.callbackLock.acquire()
        try:
            callbackStruct = Web.dataCallbacks.get(callId, None)
            if callbackStruct is None:
                raise StateError('sendDataMsgFromThread: no callbackStruct found for callId {}'.format(callId))
        finally:
            Web.callbackLock.release()
        # wait for semaphore signal indicating a callback for this callId has occured
        signaled = callbackStruct.semaphore.acquire(timeout=timeout)
        if signaled is False:
            raise TimeoutError("sendDataMessage: Data Request Timed Out({}) {}".
                               format(timeout, callbackStruct.msg))
        Web.callbackLock.acquire()
        try:
            # Remove from front of list not back to stay in order
            # Can test removing from back of list to make sure out-of-order works too
            response = callbackStruct.responses.pop(0)
            if 'data' in response:
                status = response.get('status', -1)
                numParts = response.get('numParts', 1)
                complete = (callbackStruct.numResponses == numParts and len(callbackStruct.responses) == 0)
                if complete or status != 200:
                    # End the multipart transfer
                    response['incomplete'] = False
                    Web.dataCallbacks.pop(callId, None)
                else:
                    response['incomplete'] = True
        except IndexError:
            raise StateError('sendDataMessage: callbackStruct.response is None for command {}'.
                             format(callbackStruct.msg))
        finally:
            Web.callbackLock.release()
        response['callId'] = callbackStruct.callId
        return response

    @staticmethod
    def sendDataMsgFromThread(msg, timeout=None):
        callId = Web.sendDataMsgFromThreadAsync(msg)
        response = Web.getDataMsgResponse(callId, timeout=timeout)
        return response

    @staticmethod
    def sendDataMessage(cmd):
        ''' This function is called within the ioloop thread by scheduling the call'''
        Web.wsConnLock.acquire()
        try:
            msg = json.dumps(cmd)
            Web.wsDataConn.write_message(msg)
        except Exception as err:
            errStr = 'sendDataMessage error: type {}: {}'.format(type(err), str(err))
            raise RTError(errStr)
        finally:
            Web.wsConnLock.release()

    @staticmethod
    def dataCallback(client, message):
        response = json.loads(message)
        if 'cmd' not in response:
            raise StateError('dataCallback: cmd field missing from response: {}'.format(response))
        if 'status' not in response:
            raise StateError('dataCallback: status field missing from response: {}'.format(response))
        if 'callId' not in response:
            raise StateError('dataCallback: callId field missing from response: {}'.format(response))
        status = response.get('status', -1)
        callId = response.get('callId', -1)
        origCmd = response.get('cmd', 'NoCommand')
        logging.log(DebugLevels.L6, "callback {}: {} {}".format(callId, origCmd, status))
        # Thread Synchronized Section
        Web.callbackLock.acquire()
        try:
            callbackStruct = Web.dataCallbacks.get(callId, None)
            if callbackStruct is None:
                logging.error('ProjectInterface: dataCallback callId {} not found, current callId {}'
                              .format(callId, Web.dataSequenceNum))
                return
            if callbackStruct.callId != callId:
                # This should never happen
                raise StateError('callId mismtach {} {}'.format(callbackStruct.callId, callId))
            callbackStruct.responses.append(response)
            callbackStruct.numResponses += 1
            callbackStruct.semaphore.release()
        except Exception as err:
            logging.error('ProjectInterface: dataCallback error: {}'.format(err))
            raise err
        finally:
            Web.callbackLock.release()
        if time.time() > Web.cbPruneTime:
            Web.cbPruneTime = time.time() + 60
            Web.pruneCallbacks()

    @staticmethod
    def pruneCallbacks():
        numWaitingCallbacks = len(Web.dataCallbacks)
        if numWaitingCallbacks == 0:
            return
        logging.info('Web pruneCallbacks: checking {} callbaks'.format(numWaitingCallbacks))
        Web.callbackLock.acquire()
        try:
            maxSeconds = 300
            now = time.time()
            for callId in Web.dataCallbacks.keys():
                # check how many seconds old each callback is
                cb = Web.dataCallbacks[callId]
                secondsElapsed = now - cb.timeStamp
                if secondsElapsed > maxSeconds:
                    # older than max threshold so remove
                    cb.status = 400
                    cb.error = 'Callback time exceeded max threshold {}s {}s'.format(maxSeconds, secondsElapsed)
                    cb.responses.append({'cmd': 'unknown', 'status': cb.status, 'error': cb.error})
                    for i in range(len(cb.responses)):
                        cb.semaphore.release()
                    del Web.dataCallbacks[callId]
        except Exception as err:
            logging.error('Web pruneCallbacks: error {}'.format(err))
        finally:
            Web.callbackLock.release()

    @staticmethod
    def sendUserMsgFromThread(msg):
        Web.ioLoopInst.add_callback(Web.sendUserMessage, msg)

    @staticmethod
    def sendUserMessage(msg):
        Web.wsConnLock.acquire()
        try:
            for client in Web.wsBrowserMainConns:
                client.write_message(msg)
        finally:
            Web.wsConnLock.release()

    @staticmethod
    def sendBiofeedbackMsgFromThread(msg):
        Web.ioLoopInst.add_callback(Web.sendBiofeedbackMessage, msg)

    @staticmethod
    def sendBiofeedbackMessage(msg):
        Web.wsConnLock.acquire()
        try:
            for client in Web.wsBiofeedbackConns:
                client.write_message(msg)
        finally:
            Web.wsConnLock.release()

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

    class UserHttp(tornado.web.RequestHandler):
        def get_current_user(self):
            return self.get_secure_cookie("login", max_age_days=maxDaysLoginCookieValid)

        @tornado.web.authenticated
        def get(self):
            full_path = os.path.join(Web.htmlDir, Web.webIndexPage)
            logging.log(DebugLevels.L6, 'Index request: pwd: {}'.format(full_path))
            Web.httpLock.acquire()
            try:
                self.render(full_path)
            finally:
                Web.httpLock.release()

    class BiofeedbackHttp(tornado.web.RequestHandler):
        def get_current_user(self):
            return self.get_secure_cookie("login", max_age_days=maxDaysLoginCookieValid)

        @tornado.web.authenticated
        def get(self):
            full_path = os.path.join(Web.htmlDir, Web.webBiofeedPage)
            logging.log(DebugLevels.L6, 'Subject feedback http request: pwd: {}'.format(full_path))
            Web.httpLock.acquire()
            try:
                self.render(full_path)
            finally:
                Web.httpLock.release()

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
                if Web.testMode is True:
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
            self.set_nodelay(True)
            Web.wsConnLock.acquire()
            try:
                Web.wsBiofeedbackConns.append(self)
            finally:
                Web.wsConnLock.release()

        def on_close(self):
            logging.log(DebugLevels.L1, "Biofeedback WebSocket closed")
            Web.wsConnLock.acquire()
            try:
                if self in Web.wsBiofeedbackConns:
                    Web.wsBiofeedbackConns.remove(self)
            finally:
                Web.wsConnLock.release()

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
            self.set_nodelay(True)
            Web.wsConnLock.acquire()
            try:
                Web.wsBrowserMainConns.append(self)
            finally:
                Web.wsConnLock.release()

        def on_close(self):
            logging.log(DebugLevels.L1, "User WebSocket closed")
            Web.wsConnLock.acquire()
            try:
                if self in Web.wsBrowserMainConns:
                    Web.wsBrowserMainConns.remove(self)
                else:
                    logging.log(DebugLevels.L1, "on_close: connection not in list")
            finally:
                Web.wsConnLock.release()

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
            self.set_nodelay(True)
            Web.wsConnLock.acquire()
            try:
                Web.wsEventConns.append(self)
            finally:
                Web.wsConnLock.release()

        def on_close(self):
            logging.log(DebugLevels.L1, "Event WebSocket closed")
            Web.wsConnLock.acquire()
            try:
                if self in Web.wsEventConns:
                    Web.wsEventConns.remove(self)
            finally:
                Web.wsConnLock.release()

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
            self.set_nodelay(True)
            Web.wsConnLock.acquire()
            try:
                # temporarily cache any previous connection
                prevDataConn = Web.wsDataConn
                # add new connection
                Web.wsDataConn = self
                # If there was a previous connection close it
                if prevDataConn is not None:
                    prevDataConn.close()
            except Exception as err:
                logging.error('ProjectInterface: Open Data Socket error: {}'.format(err))
            finally:
                Web.wsConnLock.release()
            print('DataWebSocket: connected {}'.format(self.request.remote_ip))

        def on_close(self):
            if Web.wsDataConn == self:
                Web.wsConnLock.acquire()
                Web.wsDataConn = None
                Web.wsConnLock.release()
                logging.log(DebugLevels.L1, "Data WebSocket closed")
            else:
                logging.log(DebugLevels.L1, "on_close: Data WebSocket mismatch")
            self.close_pending_requests()

        def close_pending_requests(self):
            Web.callbackLock.acquire()
            try:
                # signal the close to anyone waiting for replies
                callIdsToRemove = []
                for callId, cb in Web.dataCallbacks.items():
                    if cb.dataConn == self:
                        callIdsToRemove.append(callId)
                        cb.status = 499
                        cb.error = 'Client closed connection'
                        # TODO - check this logic
                        cb.responses.append({'cmd': 'unknown', 'status': cb.status, 'error': cb.error})
                        for i in range(len(cb.responses)):
                            cb.semaphore.release()
                for callId in callIdsToRemove:
                    Web.dataCallbacks.pop(callId, None)
            finally:
                Web.callbackLock.release()

        def on_message(self, message):
            try:
                Web.dataCallback(self, message)
            except Exception as err:
                logging.error('DataWebSocket: on_message error: {}'.format(err))


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
    Web.sendUserMsgFromThread(json.dumps(response))
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
            response = Web.sendDataMsgFromThread(request, timeout=localtimeout)
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
                Web.sendBiofeedbackMsgFromThread(json.dumps(request))
                # forward to main browser window
                Web.sendUserMsgFromThread(json.dumps(request))
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
        response = Web.sendDataMsgFromThread(cmd, timeout=60)
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
    if Web.wsDataConn is None:
        # A remote fileWatcher hasn't connected yet
        errStr = 'Waiting for fileWatcher to attach, please try again momentarily'
        Web.setUserError(errStr)
        return
    try:
        srcFile = request['srcFile']
        compress = request['compress']
    except KeyError as err:
        Web.setUserError("UploadFiles request missing a parameter: {}".format(err))
        return
    # get the list of file to upload
    cmd = listFilesReqStruct(srcFile)
    response = Web.sendDataMsgFromThread(cmd, timeout=10)
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
        Web.sendUserMsgFromThread(json.dumps(response))
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
        Web.sendUserMsgFromThread(json.dumps(response))
    response = {'cmd': 'uploadProgress', 'file': '------upload complete------'}
    Web.sendUserMsgFromThread(json.dumps(response))
