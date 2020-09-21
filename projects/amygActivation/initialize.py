# Purpose: finalize experiment when you're done running for the day
# Add whatever you want to do, but typically first we should make sure to 
# move and delete all sever data

import os
import glob
import numpy as np
from subprocess import call
import time
import nilearn
from scipy import stats
import scipy.io as sio
import pickle
import nibabel as nib
import argparse
import random
import sys
from datetime import datetime
from dateutil import parser

# WHEN TESTING - COMMENT OUT
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
#WHEN TESTING: UNCOMMENT TO ADD PATH TO RT-CLOUD
#sys.path.append('/Users/amennen/github/rt-cloud/')
#sys.path.append('/jukebox/norman/amennen/github/brainiak/rt-cloud/')

import rtCommon.utils as utils
from rtCommon.fileClient import FileInterface
import rtCommon.projectUtils as projUtils
from rtCommon.structDict import StructDict
#from rtCommon.dicomNiftiHandler import getTransform
from rtCommon.imageHandling import getTransform


# obtain the full path for the configuration toml file
defaultConfig = os.path.join(currPath, 'conf/amygActivation.toml')

def initialize(cfg, args):
    """ purpose: load information and add to config """

    if cfg.sessionId in (None, '') or cfg.useSessionTimestamp is True:
        cfg.useSessionTimestamp = True
        cfg.sessionId = utils.dateStr30(time.localtime())
    else:
        cfg.useSessionTimestamp = False
    # MERGE WITH PARAMS
    if args.runs != '' and args.scans != '':
        # use the run and scan numbers passed in as parameters
        cfg.runNum = [int(x) for x in args.runs.split(',')]
        cfg.scanNum = [int(x) for x in args.scans.split(',')]
    else: # when you're not specifying on the command line it's already in a list
        cfg.runNum = [int(x) for x in cfg.runNum]
        cfg.scanNum = [int(x) for x in cfg.scanNum]
    
    # GET DICOM DIRECTORY
    if cfg.buildImgPath:
        imgDirDate = datetime.now()
        dateStr = cfg.date.lower()
        if dateStr != 'now' and dateStr != 'today':
            try:
                imgDirDate = parser.parse(cfg.date)
            except ValueError as err:
                raise RequestError('Unable to parse date string {} {}'.format(cfg.date, err))
        datestr = imgDirDate.strftime("%Y%m%d")
        imgDirName = "{}.{}.{}".format(datestr, cfg.subjectName, cfg.subjectName)
        cfg.dicomDir = os.path.join(cfg.local.dicomDir,imgDirName)
    else:
        cfg.dicomDir = cfg.local.dicomDir # then the whole path was supplied
    ########
    cfg.bids_id = 'sub-{0:03d}'.format(cfg.subjectNum)
    cfg.ses_id = 'ses-{0:02d}'.format(cfg.subjectDay)
    
    # specify local directories
    cfg.local.codeDir = os.path.join(cfg.local.rtcloudDir, 'projects', cfg.projectName)
    cfg.local.dataDir = os.path.join(cfg.local.codeDir, 'data') 
    cfg.local.subject_full_day_path = os.path.join(cfg.local.dataDir, cfg.bids_id, cfg.ses_id)
    cfg.local.subject_reg_dir = os.path.join(cfg.local.subject_full_day_path, 'registration_outputs')
    cfg.local.wf_dir = os.path.join(cfg.local.dataDir, cfg.bids_id, 'ses-01', 'registration')
    cfg.local.maskDir = os.path.join(cfg.local.codeDir, 'ROI')
    cfg.subject_reg_dir = cfg.local.subject_reg_dir
    cfg.wf_dir = cfg.local.wf_dir
    cfg.n_masks = len(cfg.MASK)

    if args.filesremote: # here we will need to specify separate paths for processing
        cfg.server.codeDir = os.path.join(cfg.server.rtcloudDir, 'projects', cfg.projectName)
        cfg.server.dataDir = os.path.join(cfg.server.codeDir, cfg.server.serverDataDir)
        cfg.server.subject_full_day_path = os.path.join(cfg.server.dataDir, cfg.bids_id, cfg.ses_id)
        cfg.server.subject_reg_dir = os.path.join(cfg.server.subject_full_day_path, 'registration_outputs')
        cfg.server.wf_dir = os.path.join(cfg.server.dataDir, cfg.bids_id, 'ses-01', 'registration')
        cfg.server.maskDir = os.path.join(cfg.server.codeDir, 'ROI')
        cfg.subject_reg_dir = cfg.server.subject_reg_dir
        cfg.wf_dir = cfg.server.wf_dir
    cfg.ref_BOLD = os.path.join(cfg.wf_dir,'ref_image.nii.gz')
    cfg.MNI_ref_filename = os.path.join(cfg.wf_dir, cfg.MNI_ref_BOLD) 
    cfg.T1_to_BOLD = os.path.join(cfg.wf_dir, 'affine.txt')
    cfg.MNI_to_T1 = os.path.join(cfg.wf_dir, 'ants_t1_to_mniInverseComposite.h5')
    cfg.MASK_transformed = [''] * cfg.n_masks
    cfg.local_MASK_transformed = [''] * cfg.n_masks
    for m in np.arange(cfg.n_masks):
        mask_name = cfg.MASK[m].split('.')[0] + '_space-native.nii.gz'
        cfg.MASK_transformed[m] = os.path.join(cfg.subject_reg_dir, mask_name)
        cfg.local_MASK_transformed[m] = os.path.join(cfg.local.subject_reg_dir, mask_name)
    # get conversion to flip dicom to nifti files
    cfg.axesTransform = getTransform(('L', 'A', 'S'),('P', 'L', 'S'))
    return cfg

# this project will already have the local files included on it
# def buildSubjectFoldersOnLocal(cfg):
#     """This function transfers registration files from the fmriprep workflow path to the experiment data path
#     on the Linux machine in the scanner suite"""
#     if not os.path.exists(cfg.local.subject_full_day_path):
#         os.makedirs(cfg.local.subject_full_day_path)
#     if not os.path.exists(cfg.local.wf_dir):
#         os.makedirs(cfg.local.wf_dir)
#         print('***************************************')
#         print('CREATING WF DIRECTORY %s' % cfg.local.wf_dir)
#     print('***************************************')
#     print('MAKE SURE YOU HAVE ALREADY TRANSFERRED FMRIPREP REGISTRATION OUTPUTS HERE TO %s' % cfg.local.wf_dir)
#     print('IF YOUR FMRIPREP WORK/WORKFLOW DIR IS wf_dir, FIND OUTPUTS IN:')
#     print('T1->MNI: wf_dir/anat_preproc_wf/t1_2_mni/ants_t1_to_mniComposite.h5')
#     print('BOLD->T1: wf_dir/func_preproc_ses_01_task_examplefunc_run_01_wf/bold_reg_wf/bbreg_wf/fsl2itk_fwd/affine.txt')
#     print('T1=>BOLD: wf_dir/func_preproc_ses_01_task_examplefunc_run_01_wf/bold_reg_wf/bbreg_wf/fsl2itk_inv/affine.txt')
#     print('MNI=>T1: wf_dir/anat_preproc_wf/t1_2_mni/ants_t1_to_mniInverseComposite.h5 ')
#     print('example func: wf_dir/func_preproc_ses_01_task_examplefunc_run_01_wf/bold_reference_wf/gen_ref/ref_image.nii.gz')
#     return 

def buildSubjectFoldersOnServer(cfg):
    """This function transfers registration files from the experiment data path on the 
     Linux machine in the scanner suite to the cloud server where data is processed in real-time"""
    if not os.path.exists(cfg.server.subject_full_day_path):
        os.makedirs(cfg.server.subject_full_day_path)
    if not os.path.exists(cfg.server.wf_dir):
        os.makedirs(cfg.server.wf_dir)
    if not os.path.exists(cfg.server.subject_reg_dir):
        os.mkdir(cfg.server.subject_reg_dir)
        print('CREATING REGISTRATION DIRECTORY %s' % cfg.server.subject_reg_dir)
    return 

####################################################################################
# from initialize import *
# defaultConfig = 'conf/amygActivation.toml'
# args = StructDict({'config':defaultConfig, 'runs': '1', 'scans': '9', 'commpipe': None, 'filesremote': True})
####################################################################################

def main(argv=None):
    """
    This is the main function that is called when you run 'intialize.py'.
    
    Here, you will load the configuration settings specified in the toml configuration 
    file, initiate the class fileInterface, and set up some directories and other 
    important things through 'initialize()'
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
    argParser.add_argument('--addr', '-a', default='localhost', type=str, 
               help='server ip address')
    argParser.add_argument('--runs', '-r', default='', type=str,
                       help='Comma separated list of run numbers')
    argParser.add_argument('--scans', '-s', default='', type=str,
                       help='Comma separated list of scan number')
    args = argParser.parse_args(argv)

    # load the experiment configuration file
    cfg = utils.loadConfigFile(args.config)
    cfg = initialize(cfg, args)

    # build subject folders on server
    if args.filesremote:
        buildSubjectFoldersOnServer(cfg)

        # open up the communication pipe using 'projectInterface'
        projectComm = projUtils.initProjectComm(args.commpipe, args.filesremote)

        # initiate the 'fileInterface' class, which will allow you to read and write 
        #   files and many other things using functions found in 'fileClient.py'
        #   INPUT:
        #       [1] args.filesremote (to retrieve dicom files from the remote server)
        #       [2] projectComm (communication pipe that is set up above)
        fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projectComm)

        # next, transfer transformation files from local --> server for online processing
        projUtils.uploadFolderToCloud(fileInterface,cfg.local.wf_dir,cfg.server.wf_dir)

        # upload ROI folder to cloud server - we would need to do this if we were using
        # a standard mask, but we're not in this case
        #projUtils.uploadFolderToCloud(fileInterface,cfg.local.maskDir,cfg.server.maskDir)

        # upload all transformed masks to the cloud
        projUtils.uploadFilesFromList(fileInterface,cfg.local_MASK_transformed,cfg.subject_reg_dir)
    return 0

if __name__ == "__main__":
    """
    If 'initalize.py' is invoked as a program, then actually go through all of the 
    portions of this script. This statement is not satisfied if functions are called 
    from another script using "from initalize.py import FUNCTION"
    """    
    main()
    sys.exit(0)
