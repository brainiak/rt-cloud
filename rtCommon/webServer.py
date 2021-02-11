"""Web Server module which provides the web user interface to control and monitor experiments"""

import tornado.web
import tornado.websocket
import os
import ssl
import json
import queue
import logging
import re
import toml
import shlex
import uuid
import asyncio
import threading
import subprocess
from pathlib import Path
from rtCommon.errors import StateError
from rtCommon.utils import DebugLevels, loadConfigFile
from rtCommon.certsUtils import getCertPath, getKeyPath
from rtCommon.structDict import StructDict, recurseCreateStructDict
from rtCommon.webHttpHandlers import HttpHandler, LoginHandler, LogoutHandler, certsDir
from rtCommon.webSocketHandlers import sendWebSocketMessage, BaseWebSocketHandler
from rtCommon.webDisplayInterface import WebDisplayInterface
from rtCommon.projectServerRPC import ProjectRPCService
from rtCommon.dataInterface import uploadFilesFromList

sslCertFile = 'rtcloud.crt'
sslPrivateKey = 'rtcloud_private.key'
CommonOutputDir = '/rtfmriData/'

moduleDir = os.path.dirname(os.path.realpath(__file__))
rootDir = os.path.dirname(moduleDir)

# Note: User refers to the clinician running the experiment, so userWindow is the main
#  browser window for running the experiment.

class Web():
    """Cloud service web-interface that is the front-end to the data processing."""
    app = None
    httpServer = None
    started = False
    httpPort = 8888
    # Main html page to load
    webDir = os.path.join(rootDir, 'web/')
    htmlDir = os.path.join(webDir, 'html')
    # For synchronizing calls across threads
    ioLoopInst = None
    testMode = False
    webDisplayInterface = None

    @staticmethod
    def start(params, cfg, testMode=False):
        """Start the web server running. Function does not return."""
        if Web.app is not None:
            raise RuntimeError("Web Server already running.")
        Web.testMode = testMode
        if params.htmlDir:
            Web.htmlDir = params.htmlDir
            Web.webDir = os.path.dirname(Web.htmlDir)
        if not params.confDir:
            params.confDir = os.path.join(Web.webDir, 'conf/')
        if params.port:
            Web.httpPort = params.port
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
        # start event loop if needed
        try:
            asyncio.get_event_loop()
        except RuntimeError as err:
            # RuntimeError thrown if no current event loop
            # Start the event loop
            asyncio.set_event_loop(asyncio.new_event_loop())

        if Web.testMode is True:
            print("Listening on: http://localhost:{}".format(Web.httpPort))
            ssl_ctx = None
        else:
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(getCertPath(certsDir, sslCertFile),
                                    getKeyPath(certsDir, sslPrivateKey))
            print("Listening on: https://localhost:{}".format(Web.httpPort))

        Web.ioLoopInst = tornado.ioloop.IOLoop.current()
        Web.webDisplayInterface = WebDisplayInterface(ioLoopInst=Web.ioLoopInst)
        Web.browserRequestHandler = WsBrowserRequestHandler(Web.webDisplayInterface, params, cfg)
        # Note that some application handlers are added after the Web.app is created, including
        # 'wsData' and 'wsSubject' which can't be added until after a handler instance is created.
        # See projectServer.py where theses handlers are added.
        Web.app = tornado.web.Application([
            (r'/', HttpHandler, dict(htmlDir=Web.htmlDir, page='index.html')),
            (r'/feedback', HttpHandler, dict(htmlDir=Web.htmlDir, page='biofeedback.html')),  # shows image
            (r'/login', LoginHandler, dict(htmlDir=Web.htmlDir, page='login.html', testMode=Web.testMode)),
            (r'/logout', LogoutHandler),
            (r'/wsUser', BaseWebSocketHandler, dict(name='wsUser', callback=Web.browserRequestHandler._wsBrowserCallback)),
            (r'/wsEvents', BaseWebSocketHandler, dict(name='wsEvent', callback=params.eventCallback)),  # gets signal to change image
            (r'/src/(.*)', tornado.web.StaticFileHandler, {'path': src_root}),
            (r'/css/(.*)', tornado.web.StaticFileHandler, {'path': css_root}),
            (r'/img/(.*)', tornado.web.StaticFileHandler, {'path': img_root}),
            (r'/build/(.*)', tornado.web.StaticFileHandler, {'path': build_root}),
        ], **settings)
        Web.httpServer = tornado.httpserver.HTTPServer(Web.app, ssl_options=ssl_ctx)
        Web.httpServer.listen(Web.httpPort)
        Web.started = True
        Web.ioLoopInst.start()

    @staticmethod
    def addHandlers(handlers):
        Web.app.add_handlers(r'.*', handlers)

    @staticmethod
    def stop():
        """Stop the web server."""
        Web.ioLoopInst.add_callback(Web.ioLoopInst.stop)
        Web.app = None
        
    # Possibly use raise exception to stop a thread
    # def raise_exception(self): i.e. for stop()
        # thread_id = self.get_id() 
        # res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 
        #       ctypes.py_object(SystemExit)) 
        # if res > 1: 
        #     ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0) 
        #     print('Exception raise failure') 

    @staticmethod
    def close():
        # Currently this should never be called
        raise StateError("Web close() called")
        # closeAllConnections()


class WsBrowserRequestHandler:
    """Command handler for commands that the javascript running in the web browser can call"""
    def __init__(self, webDisplayInterface, params, cfg):
        self.webUI = webDisplayInterface
        self.runInfo = StructDict({'threadId': None, 'stopRun': False})
        self.confDir = params.confDir
        self.configFilename = None
        if not os.path.exists(self.confDir):
            os.makedirs(self.confDir)
        if type(cfg) is str:
            self.configFilename = cfg
            cfg = loadConfigFile(self.configFilename)
        self.cfg = cfg
        self.scripts = {}
        self._addScript('mainScript', params.mainScript, 'run')
        self._addScript('initScript', params.initScript, 'init')
        self._addScript('finalizeScript', params.finalizeScript, 'finalize')

    def _addScript(self, name, path, type):
        """Add the experiment script to be connected to the various run button of the
           web page. These include 'mainScript' for classification processing,
           'initScript' for session initialization, and 'finalizeScript' for
           any final processing at the end of a session.
        """
        self.scripts[name] = (path, type)

    def on_getDefaultConfig(self):
        """Return default configuration settings for the project"""
        # TODO - may need to remove certain fields that can't be jsonified
        if self.configFilename is not None and self.configFilename != '':
            cfg = loadConfigFile(self.configFilename)
        else:
            cfg = self.cfg
        self.webUI.sendConfig(cfg, filename=self.configFilename)

    def on_getDataPoints(self):
        """Return data points that have been plotted"""
        self.webUI.sendPreviousDataPoints()

    def on_clearDataPoints(self):
        """Clear all plot datapoints"""
        self.webUI.clearAllPlots()

    def on_runScript(self, name):
        """Run one of the project scripts in a separate process"""
        sessionScript, logType = self.scripts.get(name)
        if sessionScript in (None, ''):
            self._setError(f"Script {name} is not registered, cannot run script")
            return
        if self.runInfo.threadId is not None:
            self.runInfo.threadId.join(timeout=1)
            if self.runInfo.threadId.is_alive():
                self._setError("Client thread already runnning, skipping new request")
                return
            self.runInfo.threadId = None
        self.runInfo.stopRun = False
        tag = name
        self.runInfo.threadId = threading.Thread(name='sessionThread', target=self._runSession,
                                                args=(self.cfg, sessionScript, tag, logType))
        self.runInfo.threadId.setDaemon(True)
        self.runInfo.threadId.start()

    def on_stop(self):
        """Stop execution of the currently running project script (only one can run at a time)"""
        if self.runInfo.threadId is not None:
            # TODO - stopRun needs to be made global or runSesson part of this class
            self.runInfo.stopRun = True
            self.runInfo.threadId.join(timeout=1)
            if not self.runInfo.threadId.is_alive():
                self.runInfo.threadId = None
                self.runInfo.stopRun = False

    def on_uploadFiles(self, request):
        """Upload files from the dataServer to the cloud computer"""
        if self.runInfo.uploadThread is not None:
            self.runInfo.uploadThread.join(timeout=1)
            if self.runInfo.uploadThread.is_alive():
                self._setError("Upload thread already runnning, skipping new request")
                return
        self.runInfo.uploadThread = threading.Thread(name='uploadFiles',
                                                    target=self._uploadFilesHandler,
                                                    args=(request,))
        self.runInfo.uploadThread.setDaemon(True)
        self.runInfo.uploadThread.start()

    def _wsBrowserCallback(self, client, message):
        """
        The main message handler for messages received over web sockets from the web
        page javascript. It will parse the message and call the corresponding function
        above to handle the request.
        """
        # Callback functions to invoke when message received from client window connection
        request = json.loads(message)
        logging.log(DebugLevels.L3, f'browserCallback: {request}')
        # print(f'browserCallback: {request}')
        if 'config' in request:
            # Common code for any command that sends config information - retrieve the config info
            cfgData = request['config']
            newCfg = recurseCreateStructDict(cfgData)
            if newCfg is not None:
                self.cfg = newCfg
            else:
                if cfgData is None:
                    errStr = 'wsBrowserCallback: Config field is None'
                elif type(cfgData) not in (dict, list):
                    errStr = 'wsBrowserCallback: Config field wrong type {}'.format(type(cfgData))
                else:
                    errStr = 'wsBrowserCallback: Error parsing config field {}'.format(cfgData)
                self._setError(errStr)
                return
        cmd = request.get('cmd')
        functionName = 'on_' + cmd
        func = getattr(self, functionName)
        if not callable(func):
            self._setError("Web Request: unknown command " + cmd)
            return
        logging.log(DebugLevels.L3, "WEB USER CMD: %s", func)
        args = request.get('args', ())
        if args is None:  # Can happen if key 'args' exists and is set to None
            args = ()
        kwargs = request.get('kwargs', {})
        if kwargs is None:
            kwargs = {}
        # print(f'{cmd}: {args} {kwargs}')
        try:
            # The invoked functions send any results to the clients, this allows the result
            #  to go to all connected clients instead of just the client that made the request.
            res = func(*args, **kwargs)
        except Exception as err:
            errStr = 'wsBrowserCallback: ' + str(err)
            self._setError(errStr)
        return

    def _runSession(self, cfg, pyScript, tag, logType='run'):
        """
        Run the experimenter provided python script as a separate process. Forward
        the script's printed output to the web page's log message area.
        """
        # write out config file for use by pyScript
        if logType == 'run':
            configFileName = os.path.join(self.confDir, 'cfg_sub{}_day{}_run{}.toml'.
                                        format(cfg.subjectName, cfg.subjectDay, cfg.runNum[0]))
        else:
            configFileName = os.path.join(self.confDir, 'cfg_sub{}_day{}_{}.toml'.
                                        format(cfg.subjectName, cfg.subjectDay, tag))
        with open(configFileName, 'w+') as fd:
            toml.dump(cfg, fd)

        # specify -u python option to disable buffering print commands
        cmdStr = f'python -u {pyScript} -c {configFileName}'
        # add to the rtCommon dir to the PYTHONPATH env variable
        env = os.environ.copy()
        env["PYTHONPATH"] = f'{rootDir}:' + env.get("PYTHONPATH", '')
        print('###RUN: ' + cmdStr)
        cmd = shlex.split(cmdStr)
        proc = subprocess.Popen(cmd, cwd=rootDir, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
        # send running status to user web page
        self.webUI.sendRunStatus(tag + ' running')
        # start a separate thread to read the process output
        lineQueue = queue.Queue()
        outputThread = threading.Thread(target=procOutputReader, args=(proc, lineQueue))
        outputThread.setDaemon(True)
        outputThread.start()
        line = 'start'
        while(proc.poll() is None or line != ''):
            # subprocess poll returns None while subprocess is running
            if self.runInfo.stopRun is True:
                # signal the process to exit by closing stdin
                proc.stdin.close()
                proc.terminate()
                # proc.kill()
            try:
                line = lineQueue.get(block=True, timeout=1)
            except queue.Empty:
                line = ''
            if line != '':
                if logType == 'run':
                    self.webUI.userLog(line)
                else:
                    self.webUI.sessionLog(line)
                logging.info(line.rstrip())
        # processing complete, set status
        if proc.returncode != 0:
            endStatus = tag + ': An Error in the experiment script occured'
        elif self.runInfo.stopRun is True:
            endStatus = 'stopped'
        else:
            endStatus = tag + ' complete \u2714'
        self.webUI.sendRunStatus(endStatus)
        outputThread.join(timeout=1)
        if outputThread.is_alive():
            print("OutputThread failed to exit")
        return

    def _uploadFilesHandler(self, request):
        """Handle requests from the web interface to upload files to this computer."""
        global CommonOutputDir
        if 'cmd' not in request or request['cmd'] != "uploadFiles":
            raise StateError('uploadFiles: incorrect cmd request: {}'.format(request))
        try:
            srcFile = request['srcFile']
            compress = request['compress']  # TODO use compress parameter
        except KeyError as err:
            self._setError("UploadFiles request missing a parameter: {}".format(err))
            return

        # get handle to dataInterface
        dataInterface = ProjectRPCService.exposed_DataInterface

        # get the list of file to upload
        fileList = dataInterface.listFiles(srcFile)
        if len(fileList) == 0:
            # TODO - make sendUploadProgress() command
            self.webUI.sendUploadStatus('No Matching Files')
            return

        uploadFilesFromList(dataInterface, fileList, CommonOutputDir)
        # TODO - break long fileList into parts and provide periodic progress message
        # self.webUI.sendUploadStatus(fileName)
        self.webUI.sendUploadStatus('------upload complete------')

    def _setError(self, errStr):
        errStr = 'WsBrowserRequestHandler: ' + errStr
        print(errStr)
        logging.error(errStr)
        self.webUI.setUserError(errStr)


def procOutputReader(proc, lineQueue):
    """Read output from runSession process and queue into lineQueue for logging"""
    for bline in iter(proc.stdout.readline, b''):
        line = bline.decode('utf-8')
        # check if line has error in it and print to console
        if re.search('error', line, re.IGNORECASE):
            print(line)
        # send to output queue
        lineQueue.put(line)
        if line == '':
            break


def getCookieSecret(dir):
    """Used to remember users who are currently logged in."""
    filename = os.path.join(dir, 'cookie-secret')
    if os.path.exists(filename):
        with open(filename, mode='rb') as fh:
            cookieSecret = fh.read()
    else:
        cookieSecret = uuid.uuid4().bytes
        with open(filename, mode='wb') as fh:
            fh.write(cookieSecret)
    return cookieSecret
