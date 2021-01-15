import os
import logging
import threading
from rtCommon.bidsInterface import BidsInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import installLoggers


class OpenNeuroService:
    def __init__(self, args, webSocketChannelName='wsData'):
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
