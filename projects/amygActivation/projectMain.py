import os
import sys
import argparse
import logging
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
from rtCommon.mainServer import startMainServer
from rtCommon.utils import loadConfigFile, installLoggers
from rtCommon.structDict import StructDict

defaultConfig = os.path.join(currPath, 'conf/amygActivation.toml')
expScript = os.path.join(currPath, 'amygActivation.py')
initScript = os.path.join(currPath, 'initialize.py')
finalizeScript = os.path.join(currPath, 'finalize.py')

if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename=os.path.join(currPath, 'logs/webServer.log'))

    argParser = argparse.ArgumentParser()
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                           help='dicom files retrieved from remote server')
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment file (.json or .toml)')
    args = argParser.parse_args()
    # HERE: Set the path to the fMRI Python script to run here
    params = StructDict({'fmriPyScript': expScript,
                         'initScript': initScript,
                         'finalizeScript': finalizeScript,
                         'port': 8888,
                         })

    cfg = loadConfigFile(args.config)

    # start the projectInterface server
    # this will have both a web server and rpc servers to handle client requests
    startMainServer(params, args)
