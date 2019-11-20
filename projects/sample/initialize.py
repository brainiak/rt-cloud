"""-----------------------------------------------------------------------------

initialize.py (Last Updated: 11/20/2019)

The purpose of this script is to initialize the rt-cloud session. Specifically,
it will initiate any variables that need to be initiated (e.g., configuration
file) and upload any necessary files to the cloud.

-----------------------------------------------------------------------------"""

# print a short introduction on the internet window
print(""
    "-----------------------------------------------------------------------------\n"
    "The purpose of this script is to show you the ways in which you can utilize\n"
    "an initialization function. You will notice some comments printed on the\n"
    "html browser, but if you want more details please look at initalize.py.\n"
    "-----------------------------------------------------------------------------")

import os
import sys
import struct
import logging
import argparse

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

defaultConfig = os.path.join(currPath, 'conf/sample.toml')

def initialize(cfg, fileInterface, projectComm):
    """
    This funciton is called by 'main()' below. Here, we will do a demo of the
    types of things you can do in this 'initialize.py' script. For instance,
    let's say that you need to upload mask files that you are planning to
    use during your real-time experiment or a registration file that is integral
    for the analysis of your task. The point of this script is to upload files
    to the cloud that you will need for your entire scanning session.

    In this demo, things that are on the console computer will be in the folder
    'on_console'. We will transfer files to the cloud (e.g., 'on_cloud'). Here,
    everything is on the same computer but this doesn't have to be the case
    when you run your own experiment!

    INPUT:
        [1] cfg (configuration file with important variables)
        [2] fileInterface (this will allow you to call useful functions)
        [3] projectComm (communication pipe to talk with projectInterface)
    OUTPUT:
        None.
    """

    # define directories where files are on the console ('tmp/console_directory/')
    #   and where files are on the cloud ('tmp/cloud_directory')
    consoleDir = os.path.join(currPath,'tmp/console_directory/**')
    cloudDir = os.path.join(currPath,'tmp/cloud_directory')
    print("Location of console directory: \n%s\n" %consoleDir)
    print("Location of cloud directory: \n%s\n" %cloudDir)

    # before we get ahead of ourselves, we need to make sure that the necessary file
    #   types are allowed (meaning, we are able to read them in)... in this example,
    #   at the very least we need to have access to dicom and txt file types.
    # use the function 'allowedFileTypes' in 'fileClient.py' to check this!
    

    # before we continue, we should clarify the types of file types that are allowed
    #   using the function 'allowedFileTypes' in 'fileClient.py' ...ONLY the file
    #   types that are reflected here can be uploaded to the cloud
    #   INPUT: None
    #   OUTPUT:
    #       [1] allowedFileTypes (list of allowed file types)
    
    allowedFileTypes = fileInterface.allowedFileTypes()
    print(""
    "-----------------------------------------------------------------------------\n"
    "Before continuing, we should check to see the file types that are allowed.\n"
    "To verify, we will use 'allowedFileTypes'. Only these files will be uploaded\n"
    "to the cloud in the next step!!\n"
    "Allowed file types: %s" %allowedFileTypes)

    # we want to upload files from the 'console computer' to the cloud
    # to do this, we will use 'uploadFilesToCloud' from 'projectUtils'
    #   INPUT: 
    #       [1] fileInterface (this allows us to use useful functions)
    #       [2] srcDir (the source directory for the files to be moved)
    #               NOTE: you need to use ** in order to grab the files
    #       [3] outputDir (the directory where you want the files to go)
    projUtils.uploadFilesToCloud(fileInterface,consoleDir,cloudDir)

    print(""
    "-----------------------------------------------------------------------------\n"
    "INITIALIZATION COMPLETE!")

def main(argv=None):
    """
    This is the main function that is called when you run 'intialize.py'.
    Here, you will set up an important argument parser (mostly provided by 
    the toml configuration file), initiate the class fileInterface, and set
    up some directories and other important things through 'initialize()'
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

    # obtain paths for important directories (e.g. location of dicom files)
    cfg.imgDir = os.path.join(currPath, 'dicomDir')
    cfg.codeDir = currPath

    # open up the communication pipe using 'projectInterface'
    projectComm = projUtils.initProjectComm(args.commpipe, args.filesremote)
    
    # initiate the 'fileInterface' class, which will allow you to read and write 
    #   files and many other things using functions found in 'fileClient.py'
    #   INPUT:
    #       [1] args.filesremote (to retrieve dicom files from the remote server)
    #       [2] projectComm (communication pipe that is set up above)
    fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projectComm)

    # Do processing
    initialize(cfg, fileInterface, projectComm)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
