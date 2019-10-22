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


def finalize(cfg, fileInterface, projectComm):
    # Use cfg values to create directory and filenames
    # Make a set of files to download and upload
    dirName = os.path.join('/tmp/finalize', cfg.sessionId)
    for i in range(5):
        filename = os.path.join(dirName, 'fin_test{}.mat'.format(i))
        data = b'\xFF\xEE\xDD\xCC' + struct.pack("B", i)  # semi-random data
        utils.writeFile(filename, data, binary=True)
    subDirName = os.path.join(dirName, 'subdir1')
    for i in range(5):
        filename = os.path.join(subDirName, 'sub_test{}.txt'.format(i))
        text = 'test text {}'.format(i)
        utils.writeFile(filename, text, binary=False)

    # download the finalize folder from the cloud (i.e. where this code is running)
    # onto the console computer
    outputDir = '/tmp/on_console'
    projUtils.downloadFolderFromCloud(fileInterface, dirName, outputDir)

    # upload the finalize folder from the console to the cloud
    srcDir = os.path.join(outputDir, cfg.sessionId)
    outputDir = '/tmp/on_cloud'
    projUtils.uploadFolderToCloud(fileInterface, srcDir, outputDir)

    # do other processing
    print('finalize complete')


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
    finalize(cfg, fileInterface, projectComm)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
