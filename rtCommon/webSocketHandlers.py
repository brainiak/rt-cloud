import time
import json
import threading
import logging
import tornado.websocket
from rtCommon.structDict import StructDict
from rtCommon.utils import DebugLevels
from rtCommon.errors import StateError

# Maintain websocket local state (using class as a struct)
class websocketState:
    wsConnLock = threading.Lock()
    # map from wsName to list of connections, such as 'wsData': [conn1]
    wsConnectionLists = {}
    # map from wsName to callback function, such as 'wsData': dataCallback
    wsCallbacks = {}

class BaseWebSocketHandler(tornado.websocket.WebSocketHandler):
    def initialize(self, name, callback=None):
        self.name = name
        if websocketState.wsConnectionLists.get(name) is None:
            websocketState.wsConnectionLists[name] = []
        if callback is not None:
            websocketState.wsCallbacks[name] = callback
        if websocketState.wsCallbacks.get(name) is None:
            websocketState.wsCallbacks[name] = defaultWebsocketCallback

    def open(self):
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
            print(f'ws open {self.name}, list {wsConnections}')  # TODO remove this
            wsConnections.append(self)
        finally:
            websocketState.wsConnLock.release()
        print(f'{self.name} WebSocket: connected {self.request.remote_ip}')

    def on_close(self):
        logging.log(DebugLevels.L1, f"{self.name} WebSocket closed")
        websocketState.wsConnLock.acquire()
        try:
            wsConnections = websocketState.wsConnectionLists.get(self.name)
            print(f'ws close {self.name}, list {wsConnections}')  # TODO remove
            if self in wsConnections:
                wsConnections.remove(self)
            else:
                logging.log(DebugLevels.L1, f"on_close: {self.name}: connection not in list")
        finally:
            websocketState.wsConnLock.release()

    def on_message(self, message):
        client_conn = self
        callback_func = websocketState.wsCallbacks.get(self.name)
        print(f'ws on_message {self.name}, callback {callback_func}')  # TODO remove
        try:
            callback_func(client_conn, message)
        except Exception as err:
            logging.error(f'WebSocket {self.name}: on_message error: {err}')


class DataWebSocketHandler(BaseWebSocketHandler):
    def on_close(self):
        print(f'## Data websocket closed')
        super().on_close()
        # get the corresponding RequestHandler object so we can clear any waiting threads
        callback_func = websocketState.wsCallbacks.get(self.name)
        requestHandler = callback_func.__self__
        requestHandler.close_pending_requests()


def sendWebSocketMessage(wsName, msg, conn=None):
    # print(f'sendWsMessage: {wsName}, {msg}')
    websocketState.wsConnLock.acquire()
    try:
        connList = websocketState.wsConnectionLists.get(wsName)
        if connList is None:
            raise StateError(f'sendWebSocketMessage: {wsName} has no connections')
        if conn is not None:
            if conn not in connList:
                raise StateError(f'sendWebSocketMessage: {wsName} no matching connection {conn}')
            conn.write_message(msg)
        else:
            for client in connList:
                client.write_message(msg)
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
    print(f'{client.name} Callback: {cmd}')


###################
'''
Data Mesage Handler:
This is for sending requests to fileWatcher and receiving replies (kind of an RPC)
Step 1: Prepare to send request, cache a callback structure which will match with the request
Step 2: Send the request
Step 3: Get replies, match the reply to the callback structure and signal a semaphore
'''
class RequestHandler:
    def __init__(self, name):
        self.dataCallbacks = {}
        self.dataSequenceNum = 0
        self.cbPruneTime = 0
        self.callbackLock = threading.Lock()
        self.name = name

    # Step 1 - Prepare the request, record the callback struct and ID for when the reply comes
    # was sendDataMsgFromThreadAsync(msg):  - TODO remove
    def prepare_request(self, msg):
        # Get data server connection the request will be sent on
        websocketState.wsConnLock.acquire()
        try:
            wsConnections = websocketState.wsConnectionLists.get(self.name)
            if wsConnections is None or len(wsConnections) == 0:
                raise StateError("ProjectInterface: FileServer not connected. Please run the fileServer.")
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
            # Web.ioLoopInst.add_callback(Web.sendDataMessage, msg)
        return callId, reqConn

    # Step 2: Receive a reply and match up the orig callback structure, 
    #   then call semaphore release on that callback struct to trigger waiting threads
    def callback(self, client, message):
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
        self.callbackLock.acquire()
        try:
            callbackStruct = self.dataCallbacks.get(callId, None)
            if callbackStruct is None:
                logging.error('ProjectInterface: dataCallback callId {} not found, current callId {}'
                                .format(callId, self.dataSequenceNum))
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
            self.callbackLock.release()
        if time.time() > self.cbPruneTime:
            self.cbPruneTime = time.time() + 60
            self.pruneCallbacks()

    # Step 3: Caller Wait for the semaphore signal indicating a reply has been received
    def get_response(self, callId, timeout=None):
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
        except IndexError:
            raise StateError('sendDataMessage: callbackStruct.response is None for command {}'.
                                format(callbackStruct.msg))
        finally:
            self.callbackLock.release()
        response['callId'] = callbackStruct.callId
        return response

    def close_pending_requests(self):
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
                    for i in range(len(cb.responses)):
                        cb.semaphore.release()
            for callId in callIdsToRemove:
                self.dataCallbacks.pop(callId, None)
        finally:
            self.callbackLock.release()

    def pruneCallbacks(self):
        numWaitingCallbacks = len(self.dataCallbacks)
        if numWaitingCallbacks == 0:
            return
        logging.info(f'RequestHandler {self.name} pruneCallbacks: checking {numWaitingCallbacks} callbaks')
        self.callbackLock.acquire()
        try:
            maxSeconds = 300
            now = time.time()
            for callId in self.dataCallbacks.keys():
                # check how many seconds old each callback is
                cb = self.dataCallbacks[callId]
                secondsElapsed = now - cb.timeStamp
                if secondsElapsed > maxSeconds:
                    # older than max threshold so remove
                    cb.status = 400
                    cb.error = 'Callback time exceeded max threshold {}s {}s'.format(maxSeconds, secondsElapsed)
                    cb.responses.append({'cmd': 'unknown', 'status': cb.status, 'error': cb.error})
                    for i in range(len(cb.responses)):
                        cb.semaphore.release()
                    del self.dataCallbacks[callId]
        except Exception as err:
            logging.error(f'RequestHandler {self.name} pruneCallbacks: error {err}')
        finally:
            self.callbackLock.release()
