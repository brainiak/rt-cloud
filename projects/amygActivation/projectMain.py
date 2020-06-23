import os
import sys
import argparse
import logging
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
from rtCommon.utils import loadConfigFile, installLoggers
from rtCommon.structDict import StructDict
from rtCommon.projectInterface import Web

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
                         'filesremote': args.filesremote, 
                         'port': 8888,
                         })

    cfg = loadConfigFile(args.config)

    web = Web()
    web.start(params, cfg)
