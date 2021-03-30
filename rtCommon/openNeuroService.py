"""
A command-line service to be run where the where OpenNeuro data is downloaded and cached.
This service instantiates a BidsInterface object for serving the data back to the client
running in the cloud. It connects to the remote projectServer.
Once a connection is established it waits for requets and invokes the BidsInterface
functions to handle them.
"""
import os
import logging
import threading
from rtCommon.bidsInterface import BidsInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import installLoggers


class OpenNeuroService:
    """
    A class that implements the OpenNeuroService by instantiating a BidsInterface, connecting
    to the remote projectServer and servicing requests to the BidsInterface.
    """
    def __init__(self, args, webSocketChannelName='wsData'):
        """
        Uses the WsRemoteService framework to parse connection-related args and establish
        a connection to a remote projectServer. Instantiates a local version of BidsInterface
        to handle client requests coming from the projectServer connection.
        Args:
            args: Argparse args related to connecting to the remote server. These include
                "-s <server>", "-u <username>", "-p <password>", "--test", 
                "-i <retry-connection-interval>"
            webSocketChannelName: The websocket url extension used to connecy and communicate
                to the remote projectServer, e.g. 'wsData' would connect to 'ws://server:port/wsData'
        """
        # Not necessary to set the allowedDirs for BidsInterface here becasue we won't be
        #  using the DicomToBidsStream interface, leave it as none allowed (default)
        self.bidsInterface = BidsInterface(dataRemote=False)
        self.wsRemoteService = WsRemoteService(args, webSocketChannelName)
        self.wsRemoteService.addHandlerClass(BidsInterface, self.bidsInterface)

    def runDetached(self):
        """Starts the receiver in it's own thread."""
        self.recvThread = threading.Thread(name='recvThread',
                                           target=self.wsRemoteService.runForever)
        self.recvThread.setDaemon(True)
        self.recvThread.start()


if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename='logs/OpenNeuroService.log')
    # parse connection args
    connectionArgs = parseConnectionArgs()

    try:
        openNeuroService = OpenNeuroService(connectionArgs)
        # Use this command to run the service and not return control
        openNeuroService.wsRemoteService.runForever()
        # Alternately use this command to start the service in a thread and
        #  return control to main.
        # openNeuroService.runDetached()
    except Exception as err:
        print(f'Exception: {err}')
