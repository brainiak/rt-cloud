# import important modules
import os
import sys
import numpy
import uuid
import argparse

currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)

# import project modules from rt-cloud
from rtCommon.utils import loadConfigFile, stringPartialFormat
from rtCommon.clientInterface import ClientInterface
from rtCommon.bidsArchive import BidsArchive

# path for default configuration toml file
defaultConfig = os.path.join(currPath, 'conf/openNeuroClient.toml')


def doRuns(cfg, bidsInterface, subjInterface, webInterface):
    """
    Process a run of a bids dataset. The subject and run configuration
    values will be supplied by the cfg parameter.
    Args:
        cfg: configurations parsed from the project toml config file
        bidsInterface: client interface to bids data
        webInterface: client interface to user web page
    Returns: no return value
    """
    subject = cfg.subjectName
    run = cfg.runNum[0]
    entities = {'subject': subject, 'run': run, 'suffix': 'bold', 'datatype': 'func'}
    webInterface.clearRunPlot(run)
    # Create a new bids archive from the incrementals
    bidsArchivePath = os.path.join('/tmp', 'bids_archive_' + uuid.uuid4().hex)
    newArchive = BidsArchive(bidsArchivePath)
    # Initialize the bids stream
    streamId = bidsInterface.initOpenNeuroStream(cfg.dsAccessionNumber, **entities)
    numVols = bidsInterface.getNumVolumes(streamId)
    for idx in range(numVols):
        bidsIncremental = bidsInterface.getIncremental(streamId, idx)
        newArchive.appendIncremental(bidsIncremental)
        imageData = bidsIncremental.imageData
        avg_niftiData = numpy.mean(imageData)
        print("| average activation value for TR %d is %f" %(idx, avg_niftiData))
        webInterface.plotDataPoint(run, idx, float(avg_niftiData))


def main(argv=None):
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default=None, type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--yesToPrompts', '-y', default=False, action='store_true',
                           help='automatically answer tyes to any prompts')
    args = argParser.parse_args(argv)

    # load the experiment configuration file
    cfg = loadConfigFile(args.config)

    # override config file run and scan values if specified
    if args.runs is not None:
        print("runs: ", args.runs)
        cfg.runNum = [int(x) for x in args.runs.split(',')]

    # Initialize the RPC connection to the projectInterface
    # This will give us a dataInterface for retrieving files and
    # a subjectInterface for giving feedback
    clientInterfaces = ClientInterface(yesToPrompts=args.yesToPrompts)
    bidsInterface = clientInterfaces.bidsInterface
    subjInterface = clientInterfaces.subjInterface
    webInterface  = clientInterfaces.webInterface

    doRuns(cfg, bidsInterface, subjInterface, webInterface)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
