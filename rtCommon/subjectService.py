import time
import logging
import threading
from rtCommon.subjectInterface import SubjectInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import installLoggers


class SubjectService:
    def __init__(self, args, webSocketChannelName='wsSubject'):
        self.subjectInterface = SubjectInterface(subjectRemote=False)
        self.wsRemoteService = WsRemoteService(args, webSocketChannelName)
        self.wsRemoteService.addHandlerClass(SubjectInterface, self.subjectInterface)

    def runDetached(self):
        """Starts the receiver in it's own thread."""
        self.recvThread = threading.Thread(name='recvThread',
                                           target=self.wsRemoteService.runForever)
        self.recvThread.setDaemon(True)
        self.recvThread.start()


if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename='logs/SubjectService.log')
    # parse connection args
    connectionArgs = parseConnectionArgs()

    try:
        subjectService = SubjectService(connectionArgs)
        subjectService.runDetached()
    except Exception as err:
        print(f'Exception: {err}')
    
    while True:
        feedbackMsg = subjectService.subjectInterface.msgQueue.get(block=True, timeout=None)
        print("Dequeue run: {}, tr: {}, value: {}, timestamp: {}".
                format(feedbackMsg.get('runId'),
                        feedbackMsg.get('trId'),
                        feedbackMsg.get('value'),
                        feedbackMsg.get('timestamp')))