# import important modules
import os
import sys
import argparse

currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)

# import project modules from rt-cloud
from rtCommon.utils import loadConfigFile, stringPartialFormat
from rtCommon.clientInterface import ClientInterface

# path for default configuration toml file
defaultConfig = os.path.join(currPath, 'conf/openNeuro.toml')


def doRuns(cfg, bidsInterface, subjInterface, webInterface):
    # TODO - fill in processing of bids dataset
    pass


def main(argv=None):
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default='', type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--scans', '-s', default='', type=str,
                           help='Comma separated list of scan number')
    args = argParser.parse_args(argv)

    # Initialize the RPC connection to the projectInterface
    # This will give us a dataInterface for retrieving files and
    # a subjectInterface for giving feedback
    clientInterfaces = ClientInterface()
    bidsInterface = clientInterfaces.bidsInterface
    subjInterface = clientInterfaces.subjInterface
    webInterface  = clientInterfaces.webInterface

    res = bidsInterface.echo("test")
    print(res)

    # load the experiment configuration file
    # cfg = loadConfigFile(args.config)
    # doRuns(cfg, bidsInterface, subjInterface, webInterface)

    return


if __name__ == "__main__":
    main()
    sys.exit(0)
