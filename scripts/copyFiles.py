import os
import sys
import time
import glob
import shutil

#######################
# CHANGE THESE SETTINGS
#######################
srcDir = '/path/to/existing/dicoms'
dstDir = '/path/to/copy/dicoms/to'
scanNum = 5
timeDelay = 1.5  # seconds
#######################

dicomPattern = '001_0000{:02d}_000*.dcm'.format(scanNum)

# print('{} {}'.format(srcDir, dstDir))
# print(dicomPattern)

if not os.path.exists(dstDir):
    os.makedirs(dstDir)

fileList = [x for x in glob.iglob(os.path.join(srcDir, dicomPattern))]

for file in fileList:
    fileDir, filename = os.path.split(file)
    print(filename)
    try:
        time.sleep(timeDelay)
        shutil.copy(file, dstDir)
    except shutil.SameFileError:
        print("File already exists: {}".format(filename))
        sys.exit(-1)
