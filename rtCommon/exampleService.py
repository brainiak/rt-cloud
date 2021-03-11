"""
An example remote command-line service, for example as would be run at the scanner computer
or the presentation computer to receive requests from the the classification script.

This service instantiates an ExampleInterface for sending/receiving example requests
to the projectServer in the cloud. It connects to the remote projectServer. Once a connection
is established it waits for requests and invokes the ExampleInterface functions to handle them.

"""
import os
import sys
import logging
import threading
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.exampleInterface import ExampleInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import installLoggers


class ExampleService:
    def __init__(self, args, webSocketChannelName='wsData'):
        """
        Uses the WsRemoteService framework to parse connection-related args and establish
        a connection to a remote projectServer. Instantiates a local version of
        ExampleInterface to handle client requests coming from the projectServer connection.
        Args:
            args: Argparse args related to connecting to the remote server. These include
                "-s <server>", "-u <username>", "-p <password>", "--test",
                "-i <retry-connection-interval>"
            webSocketChannelName: The websocket url extension used to connect and communicate
                to the remote projectServer, 'wsData' will connect to 'ws://server:port/wsData'
        """
        self.exampleInterface = ExampleInterface(dataRemote=False)
        self.wsRemoteService = WsRemoteService(args, webSocketChannelName)
        self.wsRemoteService.addHandlerClass(ExampleInterface, self.exampleInterface)

    def runDetached(self):
        """Starts the receiver in its own thread."""
        self.recvThread = threading.Thread(name='recvThread',
                                           target=self.wsRemoteService.runForever)
        self.recvThread.setDaemon(True)
        self.recvThread.start()


if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename='logs/ExampleService.log')

    # parse connection args
    # These include: "-s <server>", "-u <username>", "-p <password>", "--test",
    #   "-i <retry-connection-interval>"
    connectionArgs = parseConnectionArgs()

    exampleService = ExampleService(connectionArgs)
    exampleService.wsRemoteService.runForever()
