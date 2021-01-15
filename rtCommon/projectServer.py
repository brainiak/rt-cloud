import os
import sys
import time
import json
import pickle
import argparse
import threading
import logging
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.webServer import Web
from rtCommon.structDict import StructDict
from rtCommon.utils import installLoggers
from rtCommon.errors import InvocationError, StateError, RequestError
from rtCommon.projectUtils import unpackDataMessage
from rtCommon.wsRemoteService import encodeByteTypeArgs, decodeByteTypeArgs
from rtCommon.projectServerRPC import startRPCThread, ProjectRPCService
from rtCommon.webSocketHandlers import RequestHandler, DataWebSocketHandler


class ProjectServer:
    """The main server for running a project. This server starts both the web server and an RPC server."""
    def __init__(self, args):
        self.started = False
        if args is None:
            args = argparse.Namespace()
        if not hasattr(args, 'test') or args.test is None:
            args.test = False
        if not hasattr(args, 'dataRemote') or args.dataRemote is None:
            args.dataRemote = False
        if not hasattr(args, 'subjectRemote') or args.subjectRemote is None:
            args.subjectRemote = False
        if not hasattr(args, 'port') or args.port is None:
            args.port = 8888
        self.args = args
        self.params = StructDict(
            {'mainScript': args.mainScript,
             'initScript': args.initScript,
             'finalizeScript': args.finalizeScript,
             'port' : args.port,
            })
        self.web = None

    def start(self):
        """Start the Web and RPC servers. This function doesn't return."""
        web = Web()
        # web.start(self.params, self.args.config, testMode=self.args.test)
        webThread = threading.Thread(name='webServerThread',
                                    target=web.start,
                                    args=(self.params, self.args.config,),
                                    kwargs={'testMode': self.args.test})
        webThread.setDaemon(True)
        webThread.start()
        # wait for the web to initialize
        while Web.started is False:
            time.sleep(0.1)
        self.web = web

        rpcHandlers = RPCHandlers(Web.ioLoopInst, Web.webDisplayInterface)
        Web.addHandlers([(r'/wsData', DataWebSocketHandler,
                          dict(name='wsData', callback=rpcHandlers.dataWsCallback))])
        Web.addHandlers([(r'/wsSubject', DataWebSocketHandler,
                          dict(name='wsSubject', callback=rpcHandlers.subjectWsCallback))])

        rpcService = ProjectRPCService(dataRemote=self.args.dataRemote,
                                       subjectRemote=self.args.subjectRemote,
                                       webUI=Web.webDisplayInterface)
        rpcService.registerDataCommFunction(rpcHandlers.dataRequest)
        rpcService.registerSubjectCommFunction(rpcHandlers.subjectRequest)
        self.started = True
        startRPCThread(rpcService, hostname='localhost', port=12345)

        # rpcThread = threading.Thread(name='rpcThread',
        #                             target=startProjectRPCThread,
        #                             args=(rpcService,),
        #                             kwargs={'hostname': 'localhost',
        #                                     'port': 12345})
        # rpcThread.setDaemon(True)
        # rpcThread.start()

    def stop(self):
        # TODO - stop RPCThread
        self.web.stop()

# TODO: Perhaps move to ProjectServerRPC?
class RPCHandlers:
    def __init__(self, ioLoopInst, webDisplayInterface):
        self.ioLoopInst = ioLoopInst
        self.webUI = webDisplayInterface
        self.handlers = {}
        self.handlers['wsData'] = RequestHandler('wsData', ioLoopInst)
        self.handlers['wsSubject'] = RequestHandler('wsSubject', ioLoopInst)

    def dataWsCallback(self, client, message):
        handler = self.handlers.get('wsData')
        if handler is None:
            raise StateError(f'RPC Handler wsData not registered')
        try:
            handler.callback(client, message)
        except Exception as err:
            self.setError('dataWsCallback: ' + format(err))

    def subjectWsCallback(self, client, message):
        handler = self.handlers.get('wsSubject')
        if handler is None:
            raise StateError(f'RPC Handler wsSubject not registered')
        try:
            handler.callback(client, message)
        except Exception as err:
            self.setError('subjectWsCallback: ' + format(err))

    def dataRequest(self, cmd, timeout=60):
        try:
            return self.handleRPCRequest('wsData', cmd, timeout)
        except Exception as err:
            self.setError('DataRequest: ' + format(err))
            raise err;

    def subjectRequest(self, cmd, timeout=60):
        try:
            return self.handleRPCRequest('wsSubject', cmd, timeout)
        except Exception as err:
            self.setError('SubjectRequest: ' + format(err))
            raise err;

    def close_pending_requests(self, channelName):
        handler = self.handlers.get(channelName)
        if handler is None:
            raise StateError(f'RPC Handler {channelName} not registered')
        try:
            handler.close_pending_requests()
        except Exception as err:
            self.setError('close_pending_requests: ' + format(err))

    def setError(self, errStr):
        errStr = 'RPC Handler: ' + errStr
        print(errStr)
        logging.error(errStr)
        self.webUI.setUserError(errStr)

    def handleRPCRequest(self, channelName, cmd, timeout=60):
        """Process RPC requests using websocket RequestHandler to send the request"""
        """Caller will catch exceptions"""
        handler = self.handlers[channelName]
        if handler is None:
            raise StateError(f'RPC Handler {channelName} not registered')
        savedError = None
        incomplete = True
        # print(f'handle request {cmd}')
        if cmd.get('cmd') == 'rpc':
            # if cmd is rpc, check and encode any byte args as base64
            cmd = encodeByteTypeArgs(cmd)
            # TODO - also encode numpy ints and floats as python ints and floats
        while incomplete:
            response = handler.doRequest(cmd, timeout)
            if response.get('status') != 200:
                errStr = 'handleDataRequest: status {}, err {}'.format(
                            response.get('status'), response.get('error'))
                self.setError(errStr)
                raise RequestError(errStr)
            try:
                data = unpackDataMessage(response)
            except Exception as err:
                errStr = 'handleDataRequest: unpackDataMessage: {}'.format(err)
                logging.error(errStr)
                if savedError is None:
                    savedError = errStr
            incomplete = response.get('incomplete', False)
            cmd['callId'] = response.get('callId', -1)
            cmd['incomplete'] = incomplete
        if savedError:
            self.setError(savedError)
            raise RequestError(savedError)
        serializationType = response.get('dataSerialization')
        if serializationType == 'json':
            if type(data) is bytes:
                data = data.decode()
            data = json.loads(data)
        elif serializationType == 'pickle':
            data = pickle.loads(data)
        return data


if __name__ == "__main__":
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--projectName', '-p', default=None, type=str,
                           help='project name')
    argParser.add_argument('--projectDir', '-d', default=None, type=str,
                           help='project directory')
    argParser.add_argument('--config', '-c', default=None, type=str,
                           help='experiment file (.json or .toml)')
    argParser.add_argument('--mainScript', '-m', default=None, type=str,
                           help='project main script')
    argParser.add_argument('--initScript', '-i', default=None, type=str,
                           help='project initialization script')
    argParser.add_argument('--finalizeScript', '-f', default=None, type=str,
                           help='project finalization script')
    argParser.add_argument('--dataRemote', '-x', default=False, action='store_true',
                           help='dicom files retrieved from remote service')
    argParser.add_argument('--subjectRemote', '-s', default=False, action='store_true',
                           help='subject feedback/response to remote service')
    argParser.add_argument('--test', '-t', default=False, action='store_true',
                           help='start webServer in test mode, unsecure')
    args = argParser.parse_args()

    if args.projectName is None:
        raise InvocationError('Must specify project name using -p parameter')
    if args.projectDir is None:
        args.projectDir = os.path.join(rootPath, 'projects', args.projectName)
    if args.config is None:
        args.config = os.path.join(args.projectDir, f'conf/{args.projectName}.toml')
    if args.mainScript is None:
        args.mainScript = os.path.join(args.projectDir, f'{args.projectName}.py')
    if args.initScript is None:
        args.initScript = os.path.join(args.projectDir, 'initialize.py')
    if args.finalizeScript is None:
        args.finalizeScript = os.path.join(args.projectDir, 'finalize.py')

    installLoggers(logging.INFO, logging.INFO, filename=os.path.join(currPath, f'logs/{args.projectName}.log'))

    # start the webServer server

    projectServer = ProjectServer(args)
    projectServer.start()
