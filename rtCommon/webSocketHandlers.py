"""This module provides classes for handling web socket communication in the web interface."""
import time
import json
import logging
import threading
import tornado.websocket
from rtCommon.structDict import StructDict
from rtCommon.utils import DebugLevels, trimDictBytes
from rtCommon.errors import StateError


# Maintain websocket local state (using class as a struct)
class websocketState:
    """A global static class (really a struct) for maintaining connection and callback information."""
    wsConnLock = threading.Lock()
    # map from wsName to list of connections, such as 'wsData': [conn1]
    wsConnectionLists = {}
    # map from wsName to callback function, such as 'wsData': dataCallback
    wsCallbacks = {}

class BaseWebSocketHandler(tornado.websocket.WebSocketHandler):
    """
    Generic web socket handler. Estabilishes and maintains a ws connection. Intitialized with 
        a callback function that gets called when messages are received on this socket instance.
    """
    def initialize(self, name, callback=None):
        """initialize method is called by Tornado with args provided to the addHandler call"""
        self.name = name
        if websocketState.wsConnectionLists.get(name) is None:
            websocketState.wsConnectionLists[name] = []
        if callback is not None:
            websocketState.wsCallbacks[name] = callback
        if websocketState.wsCallbacks.get(name) is None:
            websocketState.wsCallbacks[name] = defaultWebsocketCallback

    def open(self):
        """Called when a new client connection is established"""
        user_id = self.get_secure_cookie("login")
        if not user_id:
            logging.warning(f'websocket {self.name} authentication failed')
            response = {'cmd': 'error', 'status': 401, 'error': 'Websocket authentication failed'}
            self.write_message(json.dumps(response))
            self.close()
            return
        logging.log(DebugLevels.L1, f"{self.name} WebSocket opened")
        self.set_nodelay(True)
        websocketState.wsConnLock.acquire()
        try:
            wsConnections = websocketState.wsConnectionLists.get(self.name)
            # print(f'ws open {self.name}, list {wsConnections}')
            wsConnections.append(self)
        finally:
            websocketState.wsConnLock.release()
        print(f'{self.name} WebSocket: connected {self.request.remote_ip}')

    def on_close(self):
        """Called when the client connection is closed"""
        logging.log(DebugLevels.L1, f"{self.name} WebSocket closed")
        websocketState.wsConnLock.acquire()
        try:
            wsConnections = websocketState.wsConnectionLists.get(self.name)
            # print(f'ws close {self.name}, list {wsConnections}')
            if self in wsConnections:
                wsConnections.remove(self)
            else:
                logging.log(DebugLevels.L1, f"on_close: {self.name}: connection not in list")
        finally:
            websocketState.wsConnLock.release()

    def on_message(self, message):
        """Called when a message is received from a client connection"""
        client_conn = self
        callback_func = websocketState.wsCallbacks.get(self.name)
        try:
            callback_func(client_conn, message)
        except Exception as err:
            logging.error(f'WebSocket {self.name}: on_message error: {err}')


class DataWebSocketHandler(BaseWebSocketHandler):
    """Sub-class the base handler in order to clean up any outstanding requests on close."""
    def on_close(self):
        super().on_close()
        # get the corresponding RequestHandler object so we can clear any waiting threads
        callback_func = websocketState.wsCallbacks.get(self.name)
        requestHandler = callback_func.__self__
        requestHandler.close_pending_requests(self.name)


class RejectWebSocketHandler(tornado.websocket.WebSocketHandler):
    """
    A web socket handler that rejects connections on the web socket and returns a
    pre-configured error with the rejection reason.
    """
    def initialize(self, rejectMsg):
        self.rejectMsg = rejectMsg

    # def prepare(self):
    #     raise tornado.web.HTTPError('## wsData is local ##')
    #     return

    def open(self):
        print(f'{self.rejectMsg}')
        self.close(code=1, reason=self.rejectMsg)
        return


def sendWebSocketMessage(wsName, msg, conn=None):
    """Send messages from the web server to all clients connected on the specified wsName socket."""
    websocketState.wsConnLock.acquire()
    try:
        connList = websocketState.wsConnectionLists.get(wsName)
        if connList is not None:
            if conn is None:
                for client in connList:
                    client.write_message(msg)
            else:
                if conn not in connList:
                    raise StateError(f'sendWebSocketMessage: {wsName} no matching connection {conn}')
                conn.write_message(msg)
        else:
            logging.log(DebugLevels.L6, f'sendWebSocketMessage: {wsName} has no connectionList')
    finally:
        websocketState.wsConnLock.release()


def closeAllConnections():
    websocketState.wsConnLock.acquire()
    try:
        for wsConnections in websocketState.wsConnectionLists:
            for conn in wsConnections:
                conn.close()
        websocketState.wsConnectionLists = {}
    finally:
        websocketState.wsConnLock.release()


def defaultWebsocketCallback(client, message):
    request = json.loads(message)
    cmd = request['cmd']
    logging.log(DebugLevels.L3, f"WEBSOCKET {client.name} CMD: {cmd}")
    # print(f'{client.name} Callback: {cmd}')


###################
'''
Data Mesage Handler:
This is for sending requests to a remote service and receiving replies (kind of an RPC)
Step 1: Prepare to send request, cache a callback structure which will match with the request
Step 2: Send the request
Step 3: Get replies, match the reply to the callback structure and signal a semaphore
'''
class RequestHandler:
    """
    Class for handling remote requests (such with a remote DataInterface). Each data requests is
    given a unique ID and callbacks from the client are matched to the original request and results
    returned to the corresponding caller.
    """
    def __init__(self, name, ioLoopInst):
        self.dataCallbacks = {}
        self.dataSequenceNum = 0
        self.cbPruneTime = 0
        self.callbackLock = threading.Lock()
        self.name = name
        self.ioLoopInst = ioLoopInst

    # Top level function to make a remote request
    def doRequest(self, msg, timeout=None):
        """
        Send a request over the web socket, i.e. to the remote FileWatcher.
        This is typically the only call that a user of this class would make.
        It is the highest level call of this class, it uses the other methods to
        complete the request.
        """
        # print(f'doRequest: {msg}')
        call_id, conn = self.prepare_request(msg)
        isNewRequest = not msg.get('incomplete', False)
        cmd = msg.get('cmd')
        logging.log(DebugLevels.L6, f'wsRequest, {cmd}, call_id {call_id} newRequest {isNewRequest}')
        if isNewRequest is True:
            json_msg = json.dumps(msg)
            self.ioLoopInst.add_callback(sendWebSocketMessage, wsName=self.name, msg=json_msg, conn=conn)
        response = self.get_response(call_id, timeout=timeout)
        return response

    # Step 1 - Prepare the request, record the callback struct and ID for when the reply comes
    def prepare_request(self, msg):
        """Prepate a request to be sent, including creating a callback structure and unique ID."""
        # Get data server connection the request will be sent on
        websocketState.wsConnLock.acquire()
        try:
            wsConnections = websocketState.wsConnectionLists.get(self.name)
            if wsConnections is None or len(wsConnections) == 0:
                serviceName = 'DataService'
                if self.name == 'wsSubject':
                    serviceName = 'SubjectService'
                raise StateError(f"RemoteService: {serviceName} not connected. Please start the remote service.")
            reqConn = wsConnections[-1]  # always use most recent connection
        finally:
            websocketState.wsConnLock.release()
        callId = msg.get('callId')
        if not callId:
            callbackStruct = StructDict()
            callbackStruct.dataConn = reqConn
            callbackStruct.numResponses = 0
            callbackStruct.responses = []
            callbackStruct.semaphore = threading.Semaphore(value=0)
            callbackStruct.timeStamp = time.time()
            callbackStruct.msg = msg.copy()
            if 'data' in callbackStruct.msg:
                del callbackStruct.msg['data']
            self.callbackLock.acquire()
            try:
                self.dataSequenceNum += 1
                callId = self.dataSequenceNum
                callbackStruct.callId = callId
                msg['callId'] = callId
                self.dataCallbacks[callId] = callbackStruct
            finally:
                self.callbackLock.release()
            # self.ioLoopInst.add_callback(Web.sendDataMessage, msg)
        return callId, reqConn

    # Step 2: Receive a reply and match up the orig callback structure, 
    #   then call semaphore release on that callback struct to trigger waiting threads
    def callback(self, client, message):
        """Recieve a callback from the client and match it to the original request that was sent."""
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
        # numParts = response.get('numParts')
        # partId = response.get('partId')
        # print(f'callback {callId}: {origCmd} {status} numParts {numParts} partId {partId}')
        # Thread Synchronized Section
        self.callbackLock.acquire()
        try:
            callbackStruct = self.dataCallbacks.get(callId, None)
            if callbackStruct is None:
                # print(f'webServer: dataCallback callId {callId} not found, current callId {self.dataSequenceNum}')
                logging.error('webServer: dataCallback callId {} not found, current callId {}'
                                .format(callId, self.dataSequenceNum))
                return
            if callbackStruct.callId != callId:
                # This should never happen
                raise StateError('callId mismtach {} {}'.format(callbackStruct.callId, callId))
            callbackStruct.responses.append(response)
            callbackStruct.numResponses += 1
            callbackStruct.semaphore.release()
        except Exception as err:
            logging.error('webServer: dataCallback error: {}'.format(err))
            raise err
        finally:
            self.callbackLock.release()
        if time.time() > self.cbPruneTime:
            self.cbPruneTime = time.time() + 60
            self.pruneCallbacks()

    # Step 3: Caller Wait for the semaphore signal indicating a reply has been received
    def get_response(self, callId, timeout=None):
        """Client calls get_response() to wait for the callback results to be returned."""
        self.callbackLock.acquire()
        try:
            callbackStruct = self.dataCallbacks.get(callId, None)
            if callbackStruct is None:
                raise StateError('sendDataMsgFromThread: no callbackStruct found for callId {}'.format(callId))
        finally:
            self.callbackLock.release()
        # wait for semaphore signal indicating a callback for this callId has occured
        signaled = callbackStruct.semaphore.acquire(timeout=timeout)
        if signaled is False:
            trimDictBytes(callbackStruct.msg)
            raise TimeoutError("sendDataMessage: Data Request Timed Out({}) {}".
                                format(timeout, callbackStruct.msg))
        self.callbackLock.acquire()
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
                    self.dataCallbacks.pop(callId, None)
                else:
                    response['incomplete'] = True
            else:
                if len(callbackStruct.responses) != 0:
                    print(f'callback num responses not zero {response}')
                self.dataCallbacks.pop(callId, None)
        except IndexError:
            trimDictBytes(callbackStruct.msg)
            raise StateError('sendDataMessage: callbackStruct.response is None for command {}'.
                                format(callbackStruct.msg))
        finally:
            self.callbackLock.release()
        response['callId'] = callbackStruct.callId
        return response

    def close_pending_requests(self):
        """Close requests and signal any threads waiting for responses."""
        self.callbackLock.acquire()
        try:
            # signal the close to anyone waiting for replies
            callIdsToRemove = []
            for callId, cb in self.dataCallbacks.items():
                if cb.dataConn == self:
                    callIdsToRemove.append(callId)
                    cb.status = 499
                    cb.error = 'Client closed connection'
                    # TODO - check this logic
                    cb.responses.append({'cmd': 'unknown', 'status': cb.status, 'error': cb.error})
                    for _ in range(len(cb.responses)):
                        cb.semaphore.release()
            for callId in callIdsToRemove:
                self.dataCallbacks.pop(callId, None)
        finally:
            self.callbackLock.release()

    def pruneCallbacks(self):
        """Remove any orphaned callback structures that never got a response back."""
        numWaitingCallbacks = len(self.dataCallbacks)
        if numWaitingCallbacks == 0:
            return
        logging.info(f'RequestHandler {self.name} pruneCallbacks: checking {numWaitingCallbacks} callbaks')
        self.callbackLock.acquire()
        try:
            maxSeconds = 300
            now = time.time()
            callIdsToRemove = []
            for callId in self.dataCallbacks.keys():
                # check how many seconds old each callback is
                cb = self.dataCallbacks[callId]
                secondsElapsed = now - cb.timeStamp
                if secondsElapsed > maxSeconds:
                    # older than max threshold so remove
                    callIdsToRemove.append(callId)
                    cb.status = 400
                    cb.error = 'Callback time exceeded max threshold {}s {}s'.format(maxSeconds, secondsElapsed)
                    cb.responses.append({'cmd': 'unknown', 'status': cb.status, 'error': cb.error})
                    for _ in range(len(cb.responses)):
                        cb.semaphore.release()
            for callId in callIdsToRemove:
                self.dataCallbacks.pop(callId, None)
        except Exception as err:
            logging.error(f'RequestHandler {self.name} pruneCallbacks: error {err}')
        finally:
            self.callbackLock.release()


