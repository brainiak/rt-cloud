"""
An example command-line service to be run at the presentation computer to receive 
classification results from the classification script.

This service instantiates a SubjectInterface for serving sending/receiving subject feedback
to the projectServer in the cloud. It connects to the remote projectServer. Once a connection
is established it waits for requets and invokes the SubjecInterface functions to handle them.

Note: This service is intended as an example. In practice this subjectInterface would likely
be instantiated within the presentation script and there it would use WsRemoteService
to connect this instance to the remote projectServer where the classification is script running.
"""
import os
import sys
import logging
import threading
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.subjectInterface import SubjectInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import installLoggers


class SubjectService:
    def __init__(self, args, webSocketChannelName='wsSubject'):
        """
        Uses the WsRemoteService framework to parse connection-related args and establish
        a connection to a remote projectServer. Instantiates a local version of
        SubjectInterface to handle client requests coming from the projectServer connection.
        Args:
            args: Argparse args related to connecting to the remote server. These include
                "-s <server>", "-u <username>", "-p <password>", "--test",
                "-i <retry-connection-interval>"
            webSocketChannelName: The websocket url extension used to connecy and communicate
                to the remote projectServer, 'wsSubject' will connect to 'ws://server:port/wsSubject'
        """
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
    # These include: "-s <server>", "-u <username>", "-p <password>", "--test",
    #   "-i <retry-connection-interval>"
    connectionArgs = parseConnectionArgs()

    subjectService = SubjectService(connectionArgs)
    subjectService.runDetached()

    while True:
        feedbackMsg = subjectService.subjectInterface.msgQueue.get(block=True, timeout=None)
        print("Dequeue run: {}, tr: {}, value: {}, timestamp: {}".
                format(feedbackMsg.get('runId'),
                        feedbackMsg.get('trId'),
                        feedbackMsg.get('value'),
                        feedbackMsg.get('timestamp')))