"""-----------------------------------------------------------------------------

initialize.py (Last Updated: 11/20/2019)

The purpose of this script is to finalize the rt-cloud session. Specifically,
here we want to dowload any important files from the cloud back to the console
computer and maybe even delete files from the cloud that we don't want to 
stay there (maybe for privacy purposes).

-----------------------------------------------------------------------------"""

# print a short introduction on the internet window
print(""
    "-----------------------------------------------------------------------------\n"
    "Hooray! You are almost done! The purpose of this script is to show you how\n"
    "you can use a finalization script to download important files from the cloud\n"
    "to your console computer at the end of the experiment, as well as do anything\n"
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
    you can download an activation concatenate all of the activation values
    and then dowload only one file. You can also delete intermediate files
    you don't want to keep in the cloud for privacy reasons.

    In this demo, things are in the cloud directory and we want to move them
    to the cloud computer. Here, everything is on the same computer but this 
    doesn't have to be the case when you run your own experiment!

    INPUT:
        [1] cfg (configuration file with important variables)
        [2] fileInterface (this will allow you to call useful functions)
        [3] projectComm (communication pipe to talk with projectInterface)
    OUTPUT:
        None.
    """

    # define directories where files are on the console ('tmp/console_directory/')
    #   and where files are on the cloud ('tmp/cloud_directory')
    consoleDir = os.path.join(currPath,'tmp/console_directory/')
    cloudDir = os.path.join(currPath,'tmp/cloud_directory')
    print("Location of console directory: \n%s\n" %consoleDir)
    print("Location of cloud directory: \n%s\n" %cloudDir)

    # We first want to read in all of the .mat files that were temporarily stored
    #   on the cloud and put all of the values into a single matrix, where the
    #   first column is the TR number and the second column the activation value
    
    # However, first, we need to know the number of TRs that were sampled in order
    #   to set up the empty matrix that will store everything that we need
    #   ...we will do this by using 'listFiles' in 'fileClient.py'
    #   INPUT:
    #       [1] file pattern (which includes relative path)
    checking_filePattern = os.path.join(cloudDir,'*.mat')
    checking_fileList = fileInterface.listFiles(checking_filePattern)
    print(""
        "-----------------------------------------------------------------------------\n"
        "List of average activation files:")
    for i in np.arange(np.shape(checking_fileList)[0]):
        print('• %s'%checking_fileList[i])

    # Now we will read in the various activations from each of the .mat files and
    #   save it all into one matrix, where we also keep track of TR
    all_activations = np.zeros((np.shape(checking_fileList)[0],2))
    for i in np.arange(np.shape(checking_fileList)[0]):
        this_activation = sio.loadmat(checking_fileList[i])['value']
        all_activations[i,0] = i + 1
        all_activations[i,1] = this_activation[0][0]

    # Next, we will save the matrix into a single .mat file
    output_matFilename = os.path.join(cloudDir,'all_avg_activations.mat')
    sio.savemat(output_matFilename,{'TR':all_activations[:,0],
        'value':all_activations[:,1]})
    print(""
        "-----------------------------------------------------------------------------\n"
        "Save all of the variables (from different .mat files) into one .mat file")

    # we now want to get the newest .mat file (the one we just saved above) and download
    #   that file to the console computer ...to do this we will use the  
    print(cloudDir)
    newest_activationFile = fileInterface.getNewestFile(os.path.join(cloudDir,
        'avg_activations_*.mat'))
    
    newest_activationFile = fileInterface.getNewestFile(os.path.join(currPath,
        'tmp/cloud_directory/avg_activations_*.mat'))
    print(type(newest_activationFile))

    print("Location of the newest activation file: \n%s\n" % newest_activationFile) 


    # # Use cfg values to create directory and filenames
    # # Make a set of files to download and upload
    # dirName = os.path.join('/tmp/finalize', cfg.sessionId)
    # for i in range(5):
    #     filename = os.path.join(dirName, 'fin_test{}.mat'.format(i))
    #     data = b'\xFF\xEE\xDD\xCC' + struct.pack("B", i)  # semi-random data
    #     utils.writeFile(filename, data, binary=True)
    # subDirName = os.path.join(dirName, 'subdir1')
    # for i in range(5):
    #     filename = os.path.join(subDirName, 'sub_test{}.txt'.format(i))
    #     text = 'test text {}'.format(i)
    #     utils.writeFile(filename, text, binary=False)

    # # download the finalize folder from the cloud (i.e. where this code is running)
    # # onto the console computer
    # outputDir = '/tmp/on_console'
    # projUtils.downloadFolderFromCloud(fileInterface, dirName, outputDir)

    # # upload the finalize folder from the console to the cloud
    # srcDir = os.path.join(outputDir, cfg.sessionId)
    # outputDir = '/tmp/on_cloud'
    # projUtils.uploadFolderToCloud(fileInterface, srcDir, outputDir)

    # # do other processing
    # print('finalize complete')


def main(argv=None):
    """
    This is the main function that is called when you run 'finalize.py'.
    Here, you will set up an important argument parser (mostly provided by 
    the toml configuration file), initiate the class fileInterface, and set
    up some directories and other important things through 'finalize()'
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
    #       [2] fileInterface (this will allow you to call useful variables)
    #       [3] projectComm (communication pipe to talk with projectInterface)
    finalize(cfg, fileInterface, projectComm)
    return 0


if __name__ == "__main__":
    """
    If 'finalize.py' is called from the terminal or the equivalent, then actually go
    through all of the portions of this script. This statement is not satisfied if
    functions are called from another script using "from finalize.py import FUNCTION"
    """
    main()
    sys.exit(0)
