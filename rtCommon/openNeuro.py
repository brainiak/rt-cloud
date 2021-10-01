"""
An interface OpenNeuro data and metadata. It can download and cached OpenNeuro data for playback.
"""
import os
import json
import toml
import shutil
import boto3
from botocore.config import Config
from botocore import UNSIGNED
import rtCommon.utils as utils


class OpenNeuroCache():
    def __init__(self, cachePath="/tmp/openneuro/"):
        self.cachePath = cachePath
        self.datasetList = None
        self.s3Client = None
        os.makedirs(cachePath, exist_ok = True)

    def getCachePath(self):
        return self.cachePath

    def getS3Client(self):
        if self.s3Client is None:
            self.s3Client = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        return self.s3Client

    def getDatasetList(self, refresh=False):
        """
        Returns a list of all datasets available in OpenNeuro S3 storage
        "See https://openneuro.org/public/datasets for datasets info"
        Alternate method to access from a command line call:
            aws s3 --no-sign-request ls s3://openneuro.org/
        """
        if self.datasetList is None or refresh is True:
            s3Client = boto3.client("s3", config=Config(signature_version=UNSIGNED))
            all_dataset = s3Client.list_objects(Bucket='openneuro.org', Delimiter="/")
            self.datasetList = []
            for dataset in all_dataset.get('CommonPrefixes'):
                dsetName = dataset.get('Prefix')
                # strip training slash characters
                dsetName = dsetName.rstrip('/\\')
                self.datasetList.append(dsetName)
        return self.datasetList

    def isValidAccessionNumber(self, dsAccessionNum):
        if dsAccessionNum not in self.getDatasetList():
            print(f"{dsAccessionNum} not in the OpenNeuro S3 datasets.")
            return False
        return True

    def getSubjectList(self, dsAccessionNum):
        """
        read all files and subdirectory of this dataset
        :param dsAccessionNum: the dataset id
        :return: a list of file and subdirectory names of this dataset
        """
        if not self.isValidAccessionNumber(dsAccessionNum):
            return None
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        prefix = dsAccessionNum + '/sub-'
        dataset = s3.list_objects(Bucket='openneuro.org', Delimiter="/", Prefix=prefix)
        dataset_info = []
        for info in dataset.get('CommonPrefixes'):
            subj = info.get('Prefix')
            if subj is not None:
                subj = subj.split('sub-')[1]
                if subj is not None:
                    subj = subj.rstrip('/\\')
                    dataset_info.append(subj)
        return dataset_info

    def getDescription(self, dsAccessionNum):
        """
        Returns the description file as a python dictionary
        """
        if not self.isValidAccessionNumber(dsAccessionNum):
            return None
        self.downloadData(dsAccessionNum, downloadWholeDataset=False)
        descDict = None
        try:
            filePath = os.path.join(self.cachePath, dsAccessionNum, 'dataset_description.json')
            with open(filePath, 'r') as fp:
                descDict = json.load(fp)
        except Exception as err:
            print(f"Failed to load dataset_description.json: {err}")
        return descDict

    def getReadme(self, dsAccessionNum):
        """
        Return the contents of the README file. Downloads topleve files if needed
        """
        readme = None
        if not self.isValidAccessionNumber(dsAccessionNum):
            return None
        self.downloadData(dsAccessionNum, downloadWholeDataset=False)
        try:
            filePath = os.path.join(self.cachePath, dsAccessionNum, 'README')
            readme = utils.readFile(filePath)
        except Exception as err:
            print(f"Failed to load README: {err}")
        return readme


    def getArchivePath(self, dsAccessionNum):
        archivePath = os.path.join(self.cachePath, dsAccessionNum)
        return archivePath


    def downloadData(self, dsAccessionNum, downloadWholeDataset=False, **entities):
        """
        This command will sync the specified portion of the dataset to the cache directory.
        Note if only the accessionNum is supplied then it will just sync the top-level files.
        Sync doesn't re-download files that are already present in the directory.
        Consider using --delete which removes local cache files no longer on the remote.
        """
        if not self.isValidAccessionNumber(dsAccessionNum):
            print(f"{dsAccessionNum} not in the OpenNeuro S3 datasets.")
            return False

        includePattern = ''
        if 'subject' in entities:
            subject = entities['subject']
            if type(subject) is int:
                subject = f'{subject:02d}'
            includePattern += f'sub-{subject}/'
        if 'session' in entities:
            session = entities['session']
            if includePattern == '':
                includePattern = '*'
            if type(session) is int:
                session = f'{session:02d}'
            includePattern += f'ses-{session}/'
        if 'task' in entities:
            task = entities['task']
            includePattern += f'*task-{task}'
        if 'run' in entities:
            run = entities['run']
            if type(run) is int:
                run = f'{run:02d}'
            includePattern += f'*run-{run}'
        if 'suffix' in entities:
            suffix = entities['suffix']
            includePattern += f'*{suffix}'
        if includePattern != '' or downloadWholeDataset is True:
            includePattern += '*'

        datasetDir = os.path.join(self.cachePath, dsAccessionNum)
        awsCmd = f'aws s3 sync --no-sign-request s3://openneuro.org/{dsAccessionNum} ' \
                 f'{datasetDir} --exclude "*/*" --include "{includePattern}"'
        print(f'run {awsCmd}')
        os.system(awsCmd)
        return datasetDir

