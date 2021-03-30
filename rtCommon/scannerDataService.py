"""
A command-line service to be run where the scanner data is generated (i.e. the control
room). This service instantiates a DataInterface and BidsInterface object for serving
the data back to the client running in the cloud. It connects to the remote projectServer.
Once a connection is established it waits for requets and invokes the DataInterface or
BidsInterface functions to handle them.
"""
import os
import argparse
import logging
import threading
from rtCommon.dataInterface import DataInterface
from rtCommon.bidsInterface import BidsInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import DebugLevels, installLoggers


defaultAllowedDirs = ['/tmp', '/data']
defaultAllowedTypes = ['.dcm', '.mat', '.txt']


class ScannerDataService:
    def __init__(self, args, webSocketChannelName='wsData'):
        """
        Uses the WsRemoteService framework to parse connection-related args and establish
        a connection to a remote projectServer. Instantiates a local version of
        DataInterface and BidsInterface to handle client requests coming from the
        projectServer connection.
        Args:
            args: Argparse args related to connecting to the remote server. These include
                "-s <server>", "-u <username>", "-p <password>", "--test",
                "-i <retry-connection-interval>"
            webSocketChannelName: The websocket url extension used to connecy and communicate
                to the remote projectServer, e.g. 'wsData' would connect to 'ws://server:port/wsData'
        """
        self.dataInterface = DataInterface(dataRemote=False,
                                           allowedDirs=args.allowedDirs,
                                           allowedFileTypes=args.allowedFileTypes)
        self.bidsInterface = BidsInterface(dataRemote=False, allowedDirs=args.allowedDirs)

        self.wsRemoteService = WsRemoteService(args, webSocketChannelName)
        self.wsRemoteService.addHandlerClass(DataInterface, self.dataInterface)
        self.wsRemoteService.addHandlerClass(BidsInterface, self.bidsInterface)


if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename='logs/CRDataServer.log')

    # parse connection args
    # These include: "-s <server>", "-u <username>", "-p <password>", "--test",
    #   "-i <retry-connection-interval>"
    connectionArgs = parseConnectionArgs()

    # parse remaining args
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', action="store", dest="allowedDirs", default=defaultAllowedDirs,
                        help="Allowed directories to server files from - comma separated list")
    parser.add_argument('-f', action="store", dest="allowedFileTypes", default=defaultAllowedTypes,
                        help="Allowed file types - comma separated list")
    args, _ = parser.parse_known_args(namespace=connectionArgs)

    if type(args.allowedDirs) is str:
        args.allowedDirs = args.allowedDirs.split(',')

    if type(args.allowedFileTypes) is str:
        args.allowedFileTypes = args.allowedFileTypes.split(',')

    print("Allowed file types {}".format(args.allowedFileTypes))
    print("Allowed directories {}".format(args.allowedDirs))

    try:
        dataServer = ScannerDataService(args)
        dataServer.wsRemoteService.runForever()
    except Exception as err:
        print(f'Exception: {err}')
