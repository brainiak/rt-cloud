import os
import sys
import argparse
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
from rtCommon.utils import loadConfigFile
from rtCommon.structDict import StructDict
from web.webServer import Web

defaultConfig = os.path.join(currPath, 'conf/sample.toml')


if __name__ == "__main__":
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                           help='dicom files retrieved from remote server')
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment file (.json or .toml)')
    args = argParser.parse_args()
    # HERE: Set the path to the fMRI Python script to run here
    params = StructDict({'fmriPyScript': 'projects/sample/sample.py',
                         'filesremote': args.filesremote,
                         })

    cfg = loadConfigFile(args.config)

    web = Web()
    web.start(params, cfg)
