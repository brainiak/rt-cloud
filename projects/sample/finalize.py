"""-----------------------------------------------------------------------------

initialize.py (Last Updated: 01/16/2020)

The purpose of this script is to finalize the rt-cloud session. Specifically,
here we want to dowload any important files from the cloud back to the stimulus
computer and maybe even delete files from the cloud that we don't want to 
stay there (maybe for privacy purposes).

-----------------------------------------------------------------------------"""

# print a short introduction on the internet window
print(""
    "-----------------------------------------------------------------------------\n"
    "Hooray! You are almost done! The purpose of this script is to show you how\n"
    "you can use a finalization script to download important files from the cloud\n"
    "to your stimulus computer at the end of the experiment, as well as do anything\n"
    "else prior to completely finishing the experiment. Again, you'll find some\n"
    "comments prints on the html browser but please look at finalization.py\n"
    "if you want more details.\n"
    "-----------------------------------------------------------------------------")

import os
import sys
import struct
import logging
import argparse
import numpy as np
import scipy.io as sio

# obtain full path for current directory: '.../rt-cloud/projects/sample'
currPath = os.path.dirname(os.path.realpath(__file__))
# obtain full path for root directory: '.../rt-cloud'
rootPath = os.path.dirname(os.path.dirname(currPath))

# add the path for the root directory to your python path so that you can import
#   project modules from rt-cloud
sys.path.append(rootPath)
# import project modules from rt-cloud
import rtCommon.utils as utils
import rtCommon.projectUtils as projUtils
from rtCommon.fileClient import FileInterface

# obtain the full path for the configuration toml file
defaultConfig = os.path.join(currPath, 'conf/sample.toml')


def finalize(cfg, fileInterface, projectComm):
    """
    This function is called my 'main()' below. Here, we will do a demo of the
    types of things that you can do in this 'finalize.py' script. For instance,
    you can move intermediate files and result files from the cloud directory
    to the stimulus computer. You can also delete intermediate files at the end of
    the session, which is necessary to protect the privacy of your participants.

    In this demo, things are in the cloud directory and we want to move them
    to the local (non-cloud) stimulus computer. Here, everything is on the same 
    computer but this doesn't have to be the case when you run your own experiment!

    INPUT:
        [1] cfg (configuration file with important variables)
        [2] fileInterface (this will allow a script from the cloud to access files 
                   from the stimulus computer)
        [3] projectComm (communication pipe to talk with projectInterface)
    OUTPUT:
        None.
    """

    # define directories where files are on the stimulus ('tmp/stimulus_directory/')
    #   and where files are on the cloud ('tmp/cloud_directory')
    stimulusDir = os.path.join(currPath,'tmp/stimulus_directory/')
    cloudDir = os.path.join(currPath,'tmp/cloud_directory/')
    print("Location of stimulus directory: \n%s\n" %stimulusDir)
    print("Location of cloud directory: \n%s\n" %cloudDir)

    print(""
        "-----------------------------------------------------------------------------\n"
        "List of .mat files:")
    # we will use 'listFiles' from the 'fileClient.py' to show all of the files in the
    #   temporary cloud directory
    #   INPUT:
    #       [1] file pattern (which includes relative path)
    checking_filePattern = os.path.join(cloudDir,'*.mat')
    print(checking_filePattern)
    checking_fileList = fileInterface.listFiles(checking_filePattern)
    for i in np.arange(np.shape(checking_fileList)[0]):
        print('• %s'%checking_fileList[i])

    print("List of .txt files:")
    checking_filePattern = os.path.join(cloudDir,'*.txt')
    checking_fileList = fileInterface.listFiles(checking_filePattern)
    for i in np.arange(np.shape(checking_fileList)[0]):
        print('• %s'%checking_fileList[i])

    # let's say that you want to download all of the .txt and .mat intermediary
    #   files from the cloud directory to the stimulus computer ...to do this,
    #   use 'downloadFolderFromCloud' from 'projectUtils'
    #   INPUT: 
    #       [1] fileInterface (this will allow a script from the cloud to access files 
    #               from the stimulus computer)
    #       [2] srcDir (the file pattern for the source directory)
    #       [3] outputDir (the directory where you want the files to go)
    #       [4] deleteAfter (do you want to delete the files after copying?
    #               note that te default is False)
    srcDir = os.path.join(cloudDir,'tmp/')
    outputDir = os.path.join(stimulusDir,'tmp_files/')
    projUtils.downloadFolderFromCloud(fileInterface, srcDir, outputDir, deleteAfter=True)

    print(""
    "-----------------------------------------------------------------------------\n"
    "FINALIZATION COMPLETE!")


def main(argv=None):
    """
    This is the main function that is called when you run 'finalize.py'.
    
    Here, you will load the configuration settings specified in the toml configuration 
    file, initiate the class fileInterface, and set up some directories and other 
    important things through 'finalize()'
    """

    # define the parameters that will be recognized later on to set up fileIterface
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    # This parameter is used for projectInterface
    argParser.add_argument('--commpipe', '-q', default=None, type=str,
                           help='Named pipe to communicate with projectInterface')
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                           help='retrieve files from the remote server')
    args = argParser.parse_args(argv)

    # load the experiment configuration file
    cfg = utils.loadConfigFile(args.config)

    # open up the communication pipe using 'projectInterface'
    projectComm = projUtils.initProjectComm(args.commpipe, args.filesremote)
    
    # initiate the 'fileInterface' class, which will allow you to read and write 
    #   files and many other things using functions found in 'fileClient.py'
    #   INPUT:
    #       [1] args.filesremote (to retrieve dicom files from the remote server)
    #       [2] projectComm (communication pipe that is set up above)
    fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projectComm)

    # now that we have the necessary variables, call the function 'finalize' in
    #   order to actually start reading dicoms and doing your analyses of interest!
    #   INPUT:
    #       [1] cfg (configuration file with important variables)
    #       [2] fileInterface (this will allow a script from the cloud to access files 
    #               from the stimulus computer)
    #       [3] projectComm (communication pipe to talk with projectInterface)
    finalize(cfg, fileInterface, projectComm)
    return 0


if __name__ == "__main__":
    """
    If 'finalize.py' is invoked as a program, then actually go through all of the 
    portions of this script. This statement is not satisfied if functions are called 
    from another script using "from finalize.py import FUNCTION"
    """
    main()
    sys.exit(0)
