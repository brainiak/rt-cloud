import os
import sys
import argparse
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
from rtCommon.utils import loadConfigFile
from rtCommon.fileClient import FileInterface
import rtCommon.webClientUtils as wcutils

defaultConfig = os.path.join(currPath, 'conf/sample.toml')


def doRuns(cfg, fileInterface, webComm):
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

    print('runs: {}'.format(cfg.Runs))
    val = 0
    for idx in range(len(cfg.Runs)):
        run = cfg.Runs[idx]
        scan = cfg.ScanNums[idx]
        print('processing run {}, scan {}'.format(run, scan))
        startTR = run*10
        endTR = startTR + 10
        for tr in range(startTR, endTR):
            val += 0.03
            print('Run {}, TR {}, val {}'.format(run, tr, val))
            wcutils.sendClassicationResult(webComm, run, tr, val)
    return


def main():
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
                           help='dicom files retrieved from remote server')
    args = argParser.parse_args()

    cfg = loadConfigFile(args.config)
    if args.runs != '' and args.scans != '':
        # use the run and scan numbers passed in as parameters
        cfg.Runs = [int(x) for x in args.runs.split(',')]
        cfg.ScanNums = [int(x) for x in args.scans.split(',')]

    webComm = None
    if args.webpipe:
        webComm = wcutils.openWebServerConnection(args.webpipe)
        wcutils.watchForExit()
    fileInterface = FileInterface(filesremote=args.filesremote, webpipes=webComm)

    # Do processing
    doRuns(cfg, fileInterface, webComm)
    sys.exit(0)


if __name__ == "__main__":
    main()
