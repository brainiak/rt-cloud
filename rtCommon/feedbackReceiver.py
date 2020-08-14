import os
import sys
import time
import json
import re
import argparse
import logging
import threading
import websocket
from queue import Queue, Empty
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.utils import DebugLevels, installLoggers
from rtCommon.projectUtils import login, certFile, checkSSLCertAltName, makeSSLCertFile


class WsFeedbackReceiver:
    ''' A client that receives classification results (feedback for the subject)
        from the cloud service. The communication connection
        is made with webSockets (ws)
    '''
    serverAddr = None
    sessionCookie = None
    needLogin = True
    shouldExit = False
    validationError = None
    recvThread = None
    msgQueue = Queue()
    # Synchronizing across threads
    clientLock = threading.Lock()

    @staticmethod
    def startReceiverThread(serverAddr, retryInterval=10,
                            username=None, password=None,
                            testMode=False):
        WsFeedbackReceiver.recvThread = \
            threading.Thread(name='recvThread',
                             target=WsFeedbackReceiver.runReceiver,
                             args=(serverAddr,),
                             kwargs={'retryInterval': retryInterval,
                                     'username': username,
                                     'password': password,
                                     'testMode': testMode})
        WsFeedbackReceiver.recvThread.setDaemon(True)
        WsFeedbackReceiver.recvThread.start()

    @staticmethod
    def runReceiver(serverAddr, retryInterval=10,
                    username=None, password=None,
                    testMode=False):
        WsFeedbackReceiver.serverAddr = serverAddr
        # go into loop trying to do webSocket connection periodically
        WsFeedbackReceiver.shouldExit = False
        while not WsFeedbackReceiver.shouldExit:
            try:
                if WsFeedbackReceiver.needLogin or WsFeedbackReceiver.sessionCookie is None:
                    WsFeedbackReceiver.sessionCookie = login(serverAddr, username, password, testMode=testMode)
                wsAddr = os.path.join('wss://', serverAddr, 'wsSubject')
                if testMode:
                    print("Warning: using non-encrypted connection for test mode")
                    wsAddr = os.path.join('ws://', serverAddr, 'wsSubject')
                logging.log(DebugLevels.L6, "Trying connection: %s", wsAddr)
                ws = websocket.WebSocketApp(wsAddr,
                                            on_message=WsFeedbackReceiver.on_message,
                                            on_close=WsFeedbackReceiver.on_close,
                                            on_error=WsFeedbackReceiver.on_error,
                                            cookie="login="+WsFeedbackReceiver.sessionCookie)
                logging.log(logging.INFO, "Connected to: %s", wsAddr)
                print("Connected to: {}".format(wsAddr))
                ws.run_forever(sslopt={"ca_certs": certFile})
            except Exception as err:
                logging.log(logging.INFO, "WsFeedbackReceiver Exception {}: {}".format(type(err).__name__, str(err)))
                print('sleep {}'.format(retryInterval))
                time.sleep(retryInterval)

    @staticmethod
    def stop():
        WsFeedbackReceiver.shouldExit = True

    @staticmethod
    def on_message(client, message):
        response = {'status': 400, 'error': 'unhandled request'}
        try:
            request = json.loads(message)
            response = request.copy()
            if 'data' in response: del response['data']
            cmd = request.get('cmd')
            logging.log(logging.INFO, "{}".format(cmd))
            # Now handle requests
            if cmd == 'resultValue':
                runId = request.get('runId')
                trId = request.get('trId')
                resValue = request.get('value')
                # print("Received run: {} tr: {} value: {}".format(runId, trId, resValue))
                feedbackMsg = {'runId': runId,
                               'trId': trId,
                               'value': resValue,
                               'timestamp': time.time()
                              }
                WsFeedbackReceiver.msgQueue.put(feedbackMsg)
                response.update({'status': 200})
                return send_response(client, response)
            elif cmd == 'ping':
                response.update({'status': 200})
                return send_response(client, response)
            elif cmd == 'error':
                errorCode = request.get('status', 400)
                errorMsg = request.get('error', 'missing error msg')
                if errorCode == 401:
                    WsFeedbackReceiver.needLogin = True
                    WsFeedbackReceiver.sessionCookie = None
                errStr = 'Error {}: {}'.format(errorCode, errorMsg)
                logging.log(logging.ERROR, errStr)
                return
            else:
                errStr = 'OnMessage: Unrecognized command {}'.format(cmd)
                return send_error_response(client, response, errStr)
        except Exception as err:
            errStr = "OnMessage Exception: {}: {}".format(cmd, err)
            send_error_response(client, response, errStr)
            if cmd == 'error':
                sys.exit()
            return
        errStr = 'unhandled request'
        send_error_response(client, response, errStr)
        return

    @staticmethod
    def on_close(client):
        logging.info('connection closed')

    @staticmethod
    def on_error(client, error):
        if type(error) is KeyboardInterrupt:
            WsFeedbackReceiver.shouldExit = True
        else:
            logging.log(logging.WARNING, "on_error: WsFeedbackReceiver: {} {}".
                        format(type(error), str(error)))


def send_response(client, response):
    WsFeedbackReceiver.clientLock.acquire()
    try:
        client.send(json.dumps(response))
    finally:
        WsFeedbackReceiver.clientLock.release()


def send_error_response(client, response, errStr):
    logging.log(logging.WARNING, errStr)
    response.update({'status': 400, 'error': errStr})
    send_response(client, response)


# This just provides an example of how to use the WsFeedbackReceiver, such as in 
#  a psychoPy script. A thread would be started with WsFeedbackReceiver.runReceiver
#  as shown below, and then the main thread could wait for messages on the WsFeedbackReceiver.msgQueue
if __name__ == "__main__":
    # do arg parse for server to connect to
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
    args = parser.parse_args()

    if not re.match(r'.*:\d+', args.server):
        print("Error: Expecting server address in the form <servername:port>")
        parser.print_help()
        sys.exit()

    addr, port = args.server.split(':')
    # Check if the ssl certificate is valid for this server address
    if checkSSLCertAltName(certFile, addr) is False:
        # Addr not listed in sslCert, recreate ssl Cert
        makeSSLCertFile(addr)

    print("Server: {}, interval {}".format(args.server, args.interval))

    WsFeedbackReceiver.startReceiverThread(args.server,
                                           retryInterval=args.interval,
                                           username=args.username,
                                           password=args.password,
                                           testMode=args.test)

    while True:
        feedbackMsg = WsFeedbackReceiver.msgQueue.get(block=True, timeout=None)
        print("Dequeue run: {}, tr: {}, value: {}, timestamp: {}".
              format(feedbackMsg.get('runId'),
                     feedbackMsg.get('trId'),
                     feedbackMsg.get('value'),
                     feedbackMsg.get('timestamp')))
    