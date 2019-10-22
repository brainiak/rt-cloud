import os
import sys
import struct
import logging
import argparse
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
import rtCommon.utils as utils
import rtCommon.projectUtils as projUtils
from rtCommon.fileClient import FileInterface


logLevel = logging.INFO
defaultConfig = os.path.join(currPath, 'conf/sample.toml')


def initialize(cfg, fileInterface, projectComm):
    # Use cfg values to create directory and filenames
    # Make a set of files to download and upload
    dirName = os.path.join('/tmp/initialize', cfg.sessionId)
    for i in range(5):
        filename = os.path.join(dirName, 'init_test{}.mat'.format(i))
        data = b'\xAA\xBB\xCC\xDD' + struct.pack("B", i)  # semi-random data
        utils.writeFile(filename, data, binary=True)

    # download the files from the cloud (here) to the console computer
    srcPattern = os.path.join(dirName, '*.mat')
    outputDir = '/tmp/on_console'
    projUtils.downloadFilesFromCloud(fileInterface, srcPattern, outputDir)

    # upload the files from the console computer to the cloud
    srcPattern = '/tmp/on_console/*.mat'
    outputDir = '/tmp/on_cloud/'
    projUtils.uploadFilesToCloud(fileInterface, srcPattern, outputDir)

    # list files
    fileList = fileInterface.listFiles('/tmp/**')
    # print(fileList)

    # To get a single file
    filedata = fileInterface.getFile(os.path.join(dirName, 'init_test1.mat'))
    utils.writeFile('/tmp/test1_uploaded.mat', filedata)

    # do other processing
    print('initialization complete')


def main(argv=None):
    logger = logging.getLogger()
    logger.setLevel(logLevel)

    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    # This parameter is used for projectInterface
    argParser.add_argument('--commpipe', '-q', default=None, type=str,
                           help='Named pipe to communicate with projectInterface')
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                           help='retrieve files from the remote server')
    args = argParser.parse_args(argv)

    cfg = utils.loadConfigFile(args.config)

    projectComm = projUtils.initProjectComm(args.commpipe, args.filesremote)
    fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projectComm)

    # Do processing
    initialize(cfg, fileInterface, projectComm)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
