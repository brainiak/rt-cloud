import os
import sys
import time
import logging
import argparse
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
from rtCommon.utils import loadConfigFile
from rtCommon.fileClient import FileInterface
import rtCommon.webClientUtils as wcutils


logLevel = logging.INFO
defaultConfig = os.path.join(currPath, 'conf/sample.toml')


def doRuns(cfg, fileInterface, webComm):
    logging.info('SAMPLE: FIRST LOG MESSAGE')
    # put text files to remote server
    fileInterface.putTextFile('/tmp/samp1.txt', 'hello1')
    fileInterface.putTextFile('/tmp/samp2.txt', 'hello2')

    # read text files back
    # using getFile
    d1 = fileInterface.getFile('/tmp/samp1.txt')
    print('samp1.txt: {}'.format(d1))
    # using getNewestFile
    d2 = fileInterface.getNewestFile('/tmp/samp*.txt')
    print('samp2.txt: {}'.format(d2))

    fileInterface.putTextFile('/tmp/samp3.txt', 'hello3')
    # read using watchFile
    minFileSize = 1  # 1 byte
    fileInterface.initWatch('/tmp', 'samp*.txt', minFileSize, demoStep=0)
    d3 = fileInterface.watchFile('/tmp/samp3.txt')
    print('samp3.txt: {}'.format(d3))

    print('runs: {}'.format(cfg.runNum))
    val = 0
    for idx in range(len(cfg.runNum)):
        time.sleep(1)
        run = cfg.runNum[idx]
        scan = cfg.scanNum[idx]
        print('processing run {}, scan {}'.format(run, scan))
        startTR = run*10
        endTR = startTR + 10
        for tr in range(startTR, endTR):
            val += 0.03
            print('Run {}, TR {}, val {}'.format(run, tr, val))
            wcutils.sendResultToWeb(webComm, run, tr, val)
    logging.info('SAMPLE: LAST LOG MESSAGE')
    return


def main(argv=None):
    logger = logging.getLogger()
    logger.setLevel(logLevel)

    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default='', type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--scans', '-s', default='', type=str,
                           help='Comma separated list of scan number')
    # This parameter is used by webserver
    argParser.add_argument('--webpipe', '-w', default=None, type=str,
                           help='Named pipe to communicate with webServer')
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                           help='retrieve dicom files from the remote server')
    args = argParser.parse_args(argv)

    cfg = loadConfigFile(args.config)
    if args.runs != '' and args.scans != '':
        # use the run and scan numbers passed in as parameters
        cfg.runNum = [int(x) for x in args.runs.split(',')]
        cfg.scanNum = [int(x) for x in args.scans.split(',')]

    webComm = wcutils.initWebPipeConnection(args.webpipe, args.filesremote)
    fileInterface = FileInterface(filesremote=args.filesremote, webpipes=webComm)

    # Do processing
    doRuns(cfg, fileInterface, webComm)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
