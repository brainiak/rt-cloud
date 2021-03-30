"""
This module provides the RPC server that provides communication services to the experiment script.
Note: When using services local to the projectServer, RPCs call do one hop, client --> rpyc server (method)
      When using remote services RPC calls traverse two links, client --> rpyc server --> (via websockets) remote service
"""
import rpyc
import json
import pickle
import logging
from rpyc.utils.server import ThreadedServer
from rpyc.utils.helpers import classpartial
from rtCommon.dataInterface import DataInterface
from rtCommon.subjectInterface import SubjectInterface
from rtCommon.bidsInterface import BidsInterface
from rtCommon.exampleInterface import ExampleInterface
from rtCommon.errors import StateError, RequestError
from rtCommon.projectUtils import unpackDataMessage, npToPy
from rtCommon.wsRemoteService import encodeByteTypeArgs
from rtCommon.webSocketHandlers import RequestHandler


class ProjectRPCService(rpyc.Service):
    """
    Provides Remote Procedure Call service for the experimenter's script. This service runs
    in the projectServer to receive and handle RPC requests from the experimenter script.
    It makes available to the client a DataInterface, SubjectInterface and WebInterface.
    """
    exposed_DataInterface = None
    exposed_SubjectInterface = None
    exposed_BidsInterface = None
    exposed_WebDisplayInterface = None
    exposed_ExampleInterface = None

    def __init__(self, dataRemote=False, subjectRemote=False, webUI=None):
        """
        Args:
            dataRemote: whether file read/write requests will be handled directly by the projectServer
                or forwarded over websocket RPC to a remote service.
            subjectRemote: whether subject send/receive feedback will be handled locally within projectServer
                or forwarded over websocket RPC to a remote service.
        """
        self.dataRemote = dataRemote
        self.subjectRemote = subjectRemote
        allowedDirs = None
        allowedFileTypes = None
        if dataRemote is False:
            # Allow all file types and directories for local filesystem access
            allowedDirs=['*']
            allowedFileTypes=['*']

        # Instantiate the client service instances
        ProjectRPCService.exposed_DataInterface = DataInterface(dataRemote=dataRemote,
                                                                allowedDirs=allowedDirs,
                                                                allowedFileTypes=allowedFileTypes)
        ProjectRPCService.exposed_BidsInterface = BidsInterface(dataRemote=dataRemote,
                                                                allowedDirs=allowedDirs)
        ProjectRPCService.exposed_SubjectInterface = SubjectInterface(subjectRemote=subjectRemote)
        ProjectRPCService.exposed_WebDisplayInterface = webUI
        ProjectRPCService.exposed_ExampleInterface = ExampleInterface(dataRemote=dataRemote)

    def exposed_isDataRemote(self):
        return self.dataRemote

    def exposed_isSubjectRemote(self):
        return self.subjectRemote

    @staticmethod
    def registerDataCommFunction(commFunction):
        """
        Register the function call to forward an RPC data requests over websockets. This is the
        communication for the second hop (described above) to the remote service.
        """
        if (ProjectRPCService.exposed_DataInterface is None and
            ProjectRPCService.exposed_BidsInterface is None):
            raise StateError("ServerRPC no dataInterface instatiated yet")
        if ProjectRPCService.exposed_DataInterface is not None:
            ProjectRPCService.exposed_DataInterface.registerCommFunction(commFunction)
        if ProjectRPCService.exposed_BidsInterface is not None:
            ProjectRPCService.exposed_BidsInterface.registerCommFunction(commFunction)
        if ProjectRPCService.exposed_ExampleInterface is not None:
            ProjectRPCService.exposed_ExampleInterface.registerCommFunction(commFunction)

    @staticmethod
    def registerSubjectCommFunction(commFunction):
        """
        Register the function call to forward an RPC subject requests over websockets. This is the
        communication for the second hop (described above) to the remote service.
        """
        if ProjectRPCService.exposed_SubjectInterface is None:
            raise StateError("exposed_SubjectInterface not instatiated yet")
        ProjectRPCService.exposed_SubjectInterface.registerCommFunction(commFunction)

    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass


def startRPCThread(rpcService, hostname=None, port=12345):
    """
    This function starts the Project RPC server for communication between the projectServer
        and the experiment script.
        IT DOES NOT RETURN.
    """
    safe_attrs = rpyc.core.protocol.DEFAULT_CONFIG.get('safe_attrs')
    safe_attrs.add('__format__')

    # If ThreadedServer() function below is called with a class (or classpartial with
    #   args to fill in) then each client will get it's own instance. If an instance
    #   is passed in then all clients will share that instance.
    # For non-shared case
    #   serviceWithArgs = classpartial(ProjectRPCService, dataRemote=dataRemote)
    #   rpcService = ProjectRPCService(dataRemote, dataCommFunc)
    # Note: Currently we use a shared instance
    threadId = ThreadedServer(rpcService, hostname=hostname, port=port,
                              protocol_config={
                                  "allow_public_attrs": True,
                                  "safe_attrs": safe_attrs,
                                  "allow_pickle" : True,
                                  # "allow_getattr": True,
                                  # "allow_setattr": True,
                                  # "allow_delattr": True,
                                  # "allow_all_attrs": True,
                                  })
    threadId.start()
    return rpcService


class RPCHandlers:
    """
    Class for websocket RPC handlers. This class handles the second hop described in
        note below, namely from rpyc server to the remote service via websockets.
    Note: When using local services, RPC call do one hop, client --> rypc server object/method
          When using remote services RPC calls traverse two links, client --> rpyc server --> (via websockets) remote service
    """
    def __init__(self, ioLoopInst, webDisplayInterface):
        """
        Args:
            ioLoopInst: The tornado webserver IO event loop. This is used to send
                and synchronize web socket messages
            webDisplayInterface: Interace to web browser display, to allow showing
                error and log messages to user
        """
        self.ioLoopInst = ioLoopInst
        self.webUI = webDisplayInterface
        self.handlers = {}
        self.handlers['wsData'] = RequestHandler('wsData', ioLoopInst)
        self.handlers['wsSubject'] = RequestHandler('wsSubject', ioLoopInst)

    def dataWsCallback(self, client, message):
        """Callback for requests sent to remote service over the wsData channel"""
        handler = self.handlers.get('wsData')
        if handler is None:
            raise StateError(f'RPC Handler wsData not registered')
        try:
            handler.callback(client, message)
        except Exception as err:
            self.setError('dataWsCallback: ' + format(err))

    def subjectWsCallback(self, client, message):
        """Callback for requests sent to remote service over the wsSubject channel"""
        handler = self.handlers.get('wsSubject')
        if handler is None:
            raise StateError(f'RPC Handler wsSubject not registered')
        try:
            handler.callback(client, message)
        except Exception as err:
            self.setError('subjectWsCallback: ' + format(err))

    def dataRequest(self, cmd, timeout=60):
        """Function to initiate an outgoing data request from the RPC server to a remote service"""
        try:
            return self.handleRPCRequest('wsData', cmd, timeout)
        except Exception as err:
            self.setError('DataRequest: ' + format(err))
            raise err;

    def subjectRequest(self, cmd, timeout=60):
        """Function to initiate an outgoing subject request from the RPC server to a remote service"""
        try:
            return self.handleRPCRequest('wsSubject', cmd, timeout)
        except Exception as err:
            self.setError('SubjectRequest: ' + format(err))
            raise err;

    def close_pending_requests(self, channelName):
        """Close out all pending RPC requests when a connection is disconnected"""
        handler = self.handlers.get(channelName)
        if handler is None:
            raise StateError(f'RPC Handler {channelName} not registered')
        try:
            handler.close_pending_requests()
        except Exception as err:
            self.setError('close_pending_requests: ' + format(err))

    def setError(self, errStr):
        """Set an error messsage in the user's browser window"""
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
            # Convert numpy arguments to native python types
            cmd['args'] = npToPy(cmd.get('args', ()))
            cmd['kwargs'] = npToPy(cmd.get('kwargs', {}))
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

# # Generic start RPC Thread routine
# def startRPCThread(service, hostname=None, port=23456):
#     threadId = ThreadedServer(service, hostname=hostname, port=port,
#                               protocol_config={'allow_public_attrs': True,})
#     threadId.start()
