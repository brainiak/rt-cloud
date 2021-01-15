import os
import argparse
import logging
import brainiak.utils.fmrisim_real_time_generator as datagen
from rtCommon.dataInterface import DataInterface
from rtCommon.bidsInterface import BidsInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import DebugLevels, installLoggers


defaultAllowedDirs = ['/tmp', '/data']
defaultAllowedTypes = ['.dcm', '.mat', '.txt']


class ScannerDataService:
    def __init__(self, args, webSocketChannelName='wsData'):
        self.dataInterface = DataInterface(dataRemote=False, 
                                           allowedDirs=args.allowedDirs,
                                           allowedFileTypes=args.allowedFileTypes)
        self.wsRemoteService = WsRemoteService(args, webSocketChannelName)
        self.wsRemoteService.addHandlerClass(DataInterface, self.dataInterface)
        self.bidsInterface = BidsInterface(dataRemote=False)
        self.wsRemoteService.addHandlerClass(BidsInterface, self.bidsInterface)


if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename='logs/CRDataServer.log')
    # parse connection args
    connectionArgs = parseConnectionArgs()
    # parse remaining args
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', action="store", dest="allowedDirs", default=defaultAllowedDirs,
                        help="Allowed directories to server files from - comma separated list")
    parser.add_argument('-f', action="store", dest="allowedFileTypes", default=defaultAllowedTypes,
                        help="Allowed file types - comma separated list")
    parser.add_argument('--synthetic-data', default=False, action='store_true',
                        help='Generate synthetic data for the run')
    args, _ = parser.parse_known_args(namespace=connectionArgs)

    if type(args.allowedDirs) is str:
        args.allowedDirs = args.allowedDirs.split(',')

    if type(args.allowedFileTypes) is str:
        args.allowedFileTypes = args.allowedFileTypes.split(',')

    # if generate synthetic data
    if args.synthetic_data:
        # check if the dicoms are already created
        if not os.path.exists("/tmp/synthetic_dicom/rt_199.dcm"):
            datagen.generate_data("/tmp/synthetic_dicom", {'save_dicom': True})
    
    print("Allowed file types {}".format(args.allowedFileTypes))
    print("Allowed directories {}".format(args.allowedDirs))

    try:
        dataServer = ScannerDataService(args)
        dataServer.wsRemoteService.runForever()
    except Exception as err:
        print(f'Exception: {err}')
