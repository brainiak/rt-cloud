import os
import time
import logging
import numpy as np  # type: ignore
from rtCommon.errors import StateError
try:
    import pydicom as dicom  # type: ignore
except ModuleNotFoundError:
    import dicom  # type: ignore


def parseDicomVolume(dicomImg, sliceDim):
    '''The raw dicom file will be a 2D picture with multiple slices tiled together.
       We need to separate the slices and form a volume from them.
    '''
    sliceWidth = sliceDim
    sliceHeight = sliceDim

    image = dicomImg.pixel_array

    dicomHeight, dicomWidth = image.shape
    numSlicesPerRow = dicomWidth // sliceWidth
    numSlicesPerCol = dicomHeight // sliceHeight

    max_slices = numSlicesPerRow * numSlicesPerCol
    volume = np.full((sliceWidth, sliceHeight, max_slices), np.nan)

    sliceNum = 0
    for row in range(numSlicesPerCol):
        for col in range(numSlicesPerRow):
            if sliceNum >= max_slices:
                raise StateError('parseDicomVolume: sliceNum {} exceeds max_slices {}'
                                 .format(sliceNum, max_slices))
            rpos = row * sliceHeight
            cpos = col * sliceWidth
            slice = image[rpos: rpos+sliceHeight, cpos: cpos+sliceWidth]
            volume[:, :, sliceNum] = slice
            sliceNum += 1
    return volume


def readDicomFromBuffer(data):
    dataBytesIO = dicom.filebase.DicomBytesIO(data)
    dicomImg = dicom.dcmread(dataBytesIO)
    return dicomImg


def readDicomFromFile(filename):
    dicomImg = dicom.read_file(filename)
    return dicomImg


def readRetryDicomFromFileInterface(fileInterface, filename, timeout=5):
    retries = 0
    while retries < 5:
        retries += 1
        try:
            data = fileInterface.watchFile(filename, timeout)
            # TODO - Inject error here and see if commpipe remains open
            dicomImg = readDicomFromBuffer(data)
            # check that pixel array is complete
            dicomImg.convert_pixel_data()
            # successful
            return dicomImg
        except Exception as err:
            logging.warning("LoadImage error, retry in 100 ms: {} ".format(err))
            time.sleep(0.1)
    return None


def applyMask(volume, roiInds):
    # maskedVolume = np.zeros(volume.shape, dtype=float)
    # maskedVolume.flat[roiInds] = volume.flat[roiInds]
    maskedVolume = volume.flat[roiInds]
    return maskedVolume


def anonymizeDicom(dicomImg):
    """Anonymize header"""
    del dicomImg.PatientID
    del dicomImg.PatientAge
    del dicomImg.PatientBirthDate
    del dicomImg.PatientName
    del dicomImg.PatientSex
    del dicomImg.PatientSize
    del dicomImg.PatientWeight
    del dicomImg.PatientPosition
    del dicomImg.StudyDate
    del dicomImg.StudyTime
    del dicomImg.SeriesDate
    del dicomImg.SeriesTime
    del dicomImg.AcquisitionDate
    del dicomImg.AcquisitionTime
    del dicomImg.ContentDate
    del dicomImg.ContentTime
    del dicomImg.InstanceCreationDate
    del dicomImg.InstanceCreationTime
    del dicomImg.PerformedProcedureStepStartDate
    del dicomImg.PerformedProcedureStepStartTime
    return dicomImg


def writeDicomToBuffer(dicomImg):
    dataBytesIO = dicom.filebase.DicomBytesIO()
    dicom.filewriter.write_file(dataBytesIO, dicomImg)
    dataBytesIO.seek(0)
    data = dataBytesIO.read()
    return data

def getSubjectInterpretation(cfg):
    # load interpretation file and get it
    # will be saved in subject full day path
    filename = cfg.bids_id + '_' + cfg.ses_id + '_' + 'intepretation.txt'
    full_path_filename = cfg.subject_full_day_path + '/' + filename
    z = open(full_path_filename, "r")
    temp_interpretation = z.read()
    if 'C' in temp_interpretation:
        interpretation = 'C'
    elif 'P' in temp_interpretation:
        interpretation = 'P'
    return interpretation

def getTransform():
    target_orientation = nib.orientations.axcodes2ornt(('L', 'A', 'S'))
    dicom_orientation = nib.orientations.axcodes2ornt(('P', 'L', 'S'))
    transform = nib.orientations.ornt_transform(dicom_orientation,target_orientation)
    return transform


def convertToNifti(TRnum,scanNum,cfg,dicomData):
    #anonymizedDicom = anonymizeDicom(dicomData) # should be anonymized already
    scanNumStr = str(scanNum).zfill(2)
    fileNumStr = str(TRnum).zfill(3)
    expected_dicom_name = cfg.dicomNamePattern.format(scanNumStr,fileNumStr)
    tempNiftiDir = os.path.join(cfg.dataDir, 'tmp/convertedNiftis/')
    nameToSaveNifti = expected_dicom_name.split('.')[0] + '.nii.gz'
    fullNiftiFilename = os.path.join(tempNiftiDir, nameToSaveNifti)
    if not os.path.isfile(fullNiftiFilename): # only convert if haven't done so yet (check if doesn't exist)
       fullNiftiFilename = dnh.saveAsNiftiImage(dicomData,expected_dicom_name,cfg)
    else:
        print('SKIPPING CONVERSION FOR EXISTING NIFTI {}'.format(fullNiftiFilename))
    return fullNiftiFilename
    # ask about nifti conversion or not

def registerNewNiftiToMNI(cfg,full_nifti_name):
    # should operate over each TR
    # needs full path of nifti file to register
    base_nifti_name = full_nifti_name.split('/')[-1].split('.')[0]
    output_nifti_name = '{0}{1}_space-MNI.nii.gz'.format(cfg.subject_reg_dir,base_nifti_name)
    if not os.path.isfile(output_nifti_name): # only run this code if the file doesn't exist already
        # (1) run mcflirt with motion correction to align to bold reference
        command = 'mcflirt -in {0} -reffile {1} -out {2}{3}_MC -mats'.format(full_nifti_name,cfg.ref_BOLD,cfg.subject_reg_dir,base_nifti_name)
        #print('(1) ' + command)
        A = time.time()
        call(command,shell=True)
        B = time.time()
        print(B-A)

        # (2) run c3daffine tool to convert .mat to .txt
        command = 'c3d_affine_tool -ref {0} -src {1} {2}{3}_MC.mat/MAT_0000 -fsl2ras -oitk {4}{5}_2ref.txt'.format(cfg.ref_BOLD,full_nifti_name,cfg.subject_reg_dir,base_nifti_name,cfg.subject_reg_dir,base_nifti_name)
        #print('(2) ' + command)
        A = time.time()
        call(command,shell=True)
        B = time.time()
        print(B-A)

        # (3) combine everything with ANTs call
        command = 'antsApplyTransforms --default-value 0 --float 1 --interpolation LanczosWindowedSinc -d 3 -e 3 --input {0} --reference-image {1} --output {2}{3}_space-MNI.nii.gz --transform {4}{5}_2ref.txt --transform {6} --transform {7} -v 1'.format(full_nifti_name,cfg.MNI_ref_filename,cfg.subject_reg_dir,base_nifti_name,cfg.subject_reg_dir,base_nifti_name,cfg.BOLD_to_T1,cfg.T1_to_MNI)
        #print('(3) ' + command)
        A = time.time()
        call(command,shell=True)
        B = time.time()
        print(B-A)
    else:
        print('SKIPPING REGISTRATION FOR EXISTING NIFTI {}'.format(output_nifti_name))

    return output_nifti_name

def getDicomFileName(cfg, scanNum, fileNum):
    if scanNum < 0:
        raise ValidationError("ScanNumber not supplied of invalid {}".format(scanNum))
    
    # converting important info to strings
    scanNumStr = str(scanNum).zfill(2)
    fileNumStr = str(fileNum).zfill(3)
    
    # the naming pattern is provided in the toml file
    if cfg.dicomNamePattern is None:
        raise InvocationError("Missing config settings dicomNamePattern")
    fileName = cfg.dicomNamePattern.format(scanNumStr, fileNumStr)
    fullFileName = os.path.join(cfg.dicomDir, fileName)
    
    return fullFileName
