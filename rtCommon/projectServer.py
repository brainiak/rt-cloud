"""
Main (command-line) program for running the projectServer.
Instantiates both the web interface and an RPC server for handling client script commnds.
"""
import os
import sys
import time
import argparse
import threading
import logging
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.webServer import Web
from rtCommon.structDict import StructDict
from rtCommon.utils import installLoggers
from rtCommon.errors import InvocationError
from rtCommon.projectServerRPC import startRPCThread, ProjectRPCService, RPCHandlers
from rtCommon.webSocketHandlers import DataWebSocketHandler, RejectWebSocketHandler


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
        print(f'## Settings: dataRemote:{self.args.dataRemote}, subjectRemote:{self.args.subjectRemote}')

    def start(self):
        """Start the Web and RPC servers. This function doesn't return."""
        web = Web()
        # run in a thread - web.start(self.params, self.args.config, testMode=self.args.test)
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

        # Make the websocket RPC handlers that will forward rpyc requests to the 
        #   remote service over websocket connections
        rpcHandlers = RPCHandlers(Web.ioLoopInst, Web.webDisplayInterface)

        # Add webSocket handlers for 'wsData' and 'wsSubject' urls, e.g. wss://server:port/wsData
        if self.args.dataRemote is True:
            Web.addHandlers([(r'/wsData', DataWebSocketHandler,
                                dict(name='wsData', callback=rpcHandlers.dataWsCallback))])
        else:
            msg = 'ProjectServer in local data mode: /wsData connections not allowed (use --dataRemote)'
            Web.addHandlers([(r'/wsData', RejectWebSocketHandler, dict(rejectMsg=msg))])

        if self.args.subjectRemote is True:
            Web.addHandlers([(r'/wsSubject', DataWebSocketHandler,
                            dict(name='wsSubject', callback=rpcHandlers.subjectWsCallback))])
        else:
            msg = 'ProjectServer in local subject mode: /wsSubject connections not allowed (use --subjectRemote)'
            Web.addHandlers([(r'/wsData', RejectWebSocketHandler, dict(rejectMsg=msg))])

        # Start the rpyc RPC server that the client script connects to
        rpcService = ProjectRPCService(dataRemote=self.args.dataRemote,
                                       subjectRemote=self.args.subjectRemote,
                                       webUI=Web.webDisplayInterface)
        if self.args.dataRemote:
            rpcService.registerDataCommFunction(rpcHandlers.dataRequest)
        if self.args.subjectRemote:
            rpcService.registerSubjectCommFunction(rpcHandlers.subjectRequest)
        self.started = True
        startRPCThread(rpcService, hostname='localhost', port=12345)

    def stop(self):
        # TODO - stop RPCThread
        self.web.stop()


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
    argParser.add_argument('--dataRemote', '-rd', default=False, action='store_true',
                           help='dicom files retrieved from remote service')
    argParser.add_argument('--subjectRemote', '-rs', default=False, action='store_true',
                           help='subject feedback/response to remote service')
    argParser.add_argument('--remote', '-r', default=False, action='store_true',
                           help='user remote services for both data and subject interface')
    argParser.add_argument('--port', default=8888, type=int,
                           help='Network port that the projectServer will listen for requests on')
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
    if args.remote is True:
        args.dataRemote = True
        args.subjectRemote = True

    installLoggers(logging.INFO, logging.INFO, filename=os.path.join(currPath, f'logs/{args.projectName}.log'))

    # start the projectServer
    projectServer = ProjectServer(args)
    projectServer.start()
