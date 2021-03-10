"""
An RPC server base class for encapsulating a service class and receiving requests that
will call that encapsulated class. This is part of a remote service that communicates
with the projectServer.
"""
import os
import sys
import re
import time
import json
import pickle
import logging
import argparse
import threading
import websocket
from base64 import b64encode, b64decode
from rtCommon.remoteable import RemoteHandler
from rtCommon.projectUtils import generateDataParts
from rtCommon.utils import DebugLevels, trimDictBytes
from rtCommon.errors import RequestError
from rtCommon.projectUtils import login, certFile, checkSSLCertAltName, makeSSLCertFile

class WsRemoteService:
    remoteHandler = RemoteHandler()
    commLock = threading.Lock()
    shouldExit = False

    def __init__(self, args, channelName):
        """
        Args:
            args: Argparse args for establishing a connection to the projectServer
            channelName: the websocket channel to connect on, e.g. 'wsData'
        """
        self.channelName = channelName
        self.args = args
        self.sessionCookie = None
        self.needLogin = True
        self.started = False

        # # Starts the receiver in it's own thread
        # self.recvThread = threading.Thread(name='recvThread', target=self.wsReceiver)
        # self.recvThread.setDaemon(True)
        # self.recvThread.start()

    def addHandlerClass(self, classType, classInstance):
        """Register the class that will handle the received requests via the class type"""
        WsRemoteService.remoteHandler.registerClassInstance(classType, classInstance)

    def addHandlerClassName(self, className, classInstance):
        """Register the class that will handle the received requests via the class name"""
        WsRemoteService.remoteHandler.registerClassNameInstance(className, classInstance)

    def runForever(self):
        """Run the receiver loop. This function doesn't return."""
        # go into loop trying to do webSocket connection periodically
        args = self.args
        # print(f'args {self.args}')
        WsRemoteService.shouldExit = False
        while not WsRemoteService.shouldExit:
            try:
                if self.needLogin or self.sessionCookie is None:
                    self.sessionCookie = login(args.server, args.username, args.password, testMode=args.test)
                wsAddr = os.path.join('wss://', args.server, self.channelName)
                if args.test:
                    print("Warning: using non-encrypted connection for test mode")
                    wsAddr = os.path.join('ws://', args.server, self.channelName)
                logging.log(DebugLevels.L6, "Trying connection: %s", wsAddr)
                ws = websocket.WebSocketApp(wsAddr,
                                            on_message=WsRemoteService.on_message,
                                            on_close=WsRemoteService.on_close,
                                            on_error=WsRemoteService.on_error,
                                            cookie="login="+self.sessionCookie)
                logging.log(logging.INFO, "Connected to: %s", wsAddr)
                print("Connected to: {}".format(wsAddr))
                self.started = True
                ws.run_forever(sslopt={"ca_certs": certFile})
            except Exception as err:
                logging.log(logging.INFO, "WsRemoteService Exception {}: {}".format(type(err).__name__, str(err)))
            print('sleep {}'.format(args.interval))
            time.sleep(args.interval)

    @staticmethod
    def stop():
        WsRemoteService.shouldExit = True

    @staticmethod
    def send_response(client, response):
        WsRemoteService.commLock.acquire()
        try:
            client.send(json.dumps(response))
        finally:
            WsRemoteService.commLock.release()

    @staticmethod
    def on_message(client, message):
        """
        Main message dispatcher that will get the request from projectServer
        and call the registered handler to process the request. It will then
        return the result of the handler function back to the projectServer.
        """
        response = {'status': 400, 'error': 'unhandled request'}
        cmd = 'unknown'
        try:
            request = json.loads(message)
            request = decodeByteTypeArgs(request)
            # print(f'on_message: message {request} type: {type(request)}')
            # create the response message but without data objects
            response = request.copy()
            response.pop('data', None)
            response.pop('args', None)
            response.pop('kwargs', None)
            trimDictBytes(response)
            cmd = request.get('cmd')
            # decode any encoded byte args
            # TODO - spin off a thread for each request passing in client so the thread call client.send
            callResult = WsRemoteService.remoteHandler.runRemoteCall(request)
            # serialize the callResult
            # print(f'callresult type: {type(callResult)}')
            if isNativeType(callResult):
                if type(callResult) == bytes:
                    data = callResult
                    response['dataSerialization'] = 'bytes'
                else:
                    # encode to json and then as a byte string
                    data = json.dumps(callResult).encode()
                    response['dataSerialization'] = 'json'
            else:
                data = pickle.dumps(callResult)
                response['dataSerialization'] = 'pickle'
            # return callResult
            response['status'] = 200
            compress = False
            if len(data) > 1024 * 1024:
                compress = True
            for msgPart in generateDataParts(data, response, compress=compress):
                WsRemoteService.send_response(client, msgPart)
        except Exception as err:
            errStr = "RPC Exception: {}: {}".format(cmd, err)
            print(errStr)
            response.update({'status': 400, 'error': errStr})
            WsRemoteService.send_response(client, response)
            if cmd == 'error':
                sys.exit()
            return

    @staticmethod
    def on_error(client, error):
        if type(error) is KeyboardInterrupt:
            WsRemoteService.shouldExit = True
        else:
            logging.log(logging.WARNING, "on_error: WsRemoteService: {} {}".
                        format(type(error), str(error)))

    @staticmethod
    def on_close(client, code, reason):
        print('## Connection closed, check if projectServer allows remote services.')
        print('## May need to restart projectServer with --dataRemote --subjectRemote options.')
        logging.info(f'Connection closed {code} {reason}')


def isNativeType(var):
    nativeTypes = (int, float, str, bytes, list, dict, set, tuple, bytearray, memoryview, range, complex)
    if type(var) in nativeTypes:
        return True
    return False


def encodeByteTypeArgs(cmd) -> dict:
    """
    Check if any args are of type 'bytes' and if so base64 encode them.
    The original arg will be replaced with a tag that will reference the encoded bytes
        within the cmd dict.
    Args:
        cmd: a dictionary of the command to check
    Returns:
        A cmd dictionary with the byte args encoded
    """
    args = cmd.get('args', ())
    byteArgIndices = []
    for i, arg in enumerate(args):
        if type(arg) is bytes:
            byteArgIndices.append(i)

    if len(byteArgIndices) != 0:
        # convert args from tuple to list so we can modify it
        args = list(args)
        for i in byteArgIndices:
            # encode as base64 and put a tag holder in place
            encdata = b64encode(args[i]).decode('utf-8')
            tag = 'encodedBytes_' + str(i)
            args[i] = tag
            cmd[tag] = encdata
        cmd['args'] = tuple(args)
        cmd['encodedByteArgs'] = byteArgIndices

    # Check and encode keyword args also
    kwargs = cmd.get('kwargs', {})
    byteKwargKeys = []
    for key, arg in kwargs.items():
        if type(arg) is bytes:
            byteKwargKeys.append(key)
            encdata = b64encode(arg).decode('utf-8')
            kwargs[key] = encdata
    if len(byteKwargKeys) != 0:
        cmd['encodedByteKwargs'] = byteKwargKeys
        cmd['kwargs'] = kwargs

    return cmd


def decodeByteTypeArgs(cmd) -> dict:
    """
    Decodes rpc args that were previously encoded with encodeByteTypeArgs.
    Args:
        cmd: a dictionary with encoded args
    Returns:
        cmd: a dictionary with decoded args
    """
    byteArgIndices = cmd.get('encodedByteArgs')
    if byteArgIndices is not None:
        args = cmd.get('args', ())
        args = list(args)
        for i in byteArgIndices:
            tag = 'encodedBytes_' + str(i)
            encdata = cmd.get(tag)
            if encdata is None or args[i] != tag:
                raise RequestError(f'Byte encoded data error: index {i} tag {tag}')
            decodedData = b64decode(encdata)
            args[i] = decodedData
            cmd.pop(tag, None)
        cmd.pop('encodedByteArgs')
        cmd['args'] = tuple(args)
    return cmd


def parseConnectionArgs():
    # parse args for client to connect to server
    # argv = sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', action="store", dest="server", default="localhost:8888",
                        help="Server Address with Port [server:port]")
    parser.add_argument('-i', action="store", dest="interval", type=int, default=5,
                        help="Retry connection interval (seconds)")
    parser.add_argument('-u', '--username', action="store", dest="username", default=None,
                        help="rtcloud website username")
    parser.add_argument('-p', '--password', action="store", dest="password", default=None,
                        help="rtcloud website password")
    parser.add_argument('--test', default=False, action='store_true',
                        help='Use unsecure non-encrypted connection')
    args, _ = parser.parse_known_args()

    if not re.match(r'.*:\d+', args.server):
        print("Error: Expecting server address in the form <servername:port>")
        parser.print_help()
        sys.exit()

    # Check if the ssl certificate is valid for this server address
    addr, _ = args.server.split(':')
    if checkSSLCertAltName(certFile, addr) is False:
        # Addr not listed in sslCert, recreate ssl Cert
        makeSSLCertFile(addr)

    return args
