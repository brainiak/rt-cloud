"""
An interface to access OpenNeuro data and metadata. It can download
and cache OpenNeuro data for playback.
"""
import os
import json
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
        """
        Returns an s3 client in order to reuse the same s3 client without
        always creating a new one. Not thread safe currently.
        """
        if self.s3Client is None:
            self.s3Client = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        return self.s3Client

    def getDatasetList(self, refresh=False):
        """
        Returns a list of all datasets available in OpenNeuro S3 storage.
        See https://openneuro.org/public/datasets for datasets info.
        Alternate method to access from a command line call:
        [aws s3 --no-sign-request ls s3://openneuro.org/]
        """
        if self.datasetList is None or len(self.datasetList)==0 or refresh is True:
            s3Client = boto3.client("s3", config=Config(signature_version=UNSIGNED))
            all_datasets = s3Client.list_objects(Bucket='openneuro.org', Delimiter="/")
            self.datasetList = []
            for dataset in all_datasets.get('CommonPrefixes'):
                dsetName = dataset.get('Prefix')
                # strip trailing slash characters
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
        Returns a list of all the subjects in a dataset

        Args:
            dsAccessionNum: accession number of dataset to lookup

        Returns:
            list of subjects in that dataset
        """
        if not self.isValidAccessionNumber(dsAccessionNum):
            return None
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        prefix = dsAccessionNum + '/sub-'
        dsSubjDirs = s3.list_objects(Bucket='openneuro.org', Delimiter="/", Prefix=prefix)
        subjects = []
        for info in dsSubjDirs.get('CommonPrefixes'):
            subj = info.get('Prefix')
            if subj is not None:
                subj = subj.split('sub-')[1]
                if subj is not None:
                    subj = subj.rstrip('/\\')
                    subjects.append(subj)
        return subjects

    def getDescription(self, dsAccessionNum):
        """
        Returns the dataset description file as a python dictionary
        """
        if not self.isValidAccessionNumber(dsAccessionNum):
            return None
        dsDir = self.downloadData(dsAccessionNum, downloadWholeDataset=False)
        filePath = os.path.join(dsDir, 'dataset_description.json')
        descDict = None
        try:
            with open(filePath, 'r') as fp:
                descDict = json.load(fp)
        except Exception as err:
            print(f"Failed to load dataset_description.json: {err}")
        return descDict

    def getReadme(self, dsAccessionNum):
        """
        Return the contents of the dataset README file.
        Downloads toplevel dataset files if needed.
        """
        if not self.isValidAccessionNumber(dsAccessionNum):
            return None
        dsDir = self.downloadData(dsAccessionNum, downloadWholeDataset=False)
        filePath = os.path.join(dsDir, 'README')
        readme = None
        try:
            readme = utils.readFile(filePath)
        except Exception as err:
            print(f"Failed to load README: {err}")
        return readme


    def getArchivePath(self, dsAccessionNum):
        """Returns the directory path to the cached dataset files"""
        archivePath = os.path.join(self.cachePath, dsAccessionNum)
        return archivePath


    def downloadData(self, dsAccessionNum, downloadWholeDataset=False, **entities):
        """
        This command will sync the specified portion of the dataset to the cache directory.
        Note: if only the accessionNum is supplied then it will just sync the top-level files.
        Sync doesn't re-download files that are already present in the directory.
        Consider using --delete which removes local cache files no longer on the remote.

        Args:
            dsAccessionNum: accession number of the dataset to download data for.
            downloadWholeDataset: boolean, if true all files in the dataset
                will be downloaded.
            entities: BIDS entities (subject, session, task, run, suffix) that
                define the particular subject/run of the data to download.
        Returns:
            Path to the directory containing the downloaded dataset data.
        """
        if not self.isValidAccessionNumber(dsAccessionNum):
            print(f"{dsAccessionNum} not in the OpenNeuro S3 datasets.")
            return False

        includePattern = ''
        if 'subject' in entities:
            subject = entities['subject']
            if subject != '':
                includePattern += f'sub-{subject}/'
        if 'session' in entities:
            session = entities['session']
            if session != '':
                if includePattern == '':
                    includePattern = '*'
                includePattern += f'ses-{session}/'
        if 'task' in entities:
            task = entities['task']
            if task != '':
                includePattern += f'*task-{task}'
        if 'run' in entities:
            run = entities['run']
            includePattern += f'*run-{run}'
        if 'suffix' in entities:
            suffix = entities['suffix']
            if suffix != '':
                includePattern += f'*{suffix}'
        if includePattern != '' or downloadWholeDataset is True:
            includePattern += '*'

        datasetDir = os.path.join(self.cachePath, dsAccessionNum)
        awsCmd = f'aws s3 sync --no-sign-request s3://openneuro.org/{dsAccessionNum} ' \
                 f'{datasetDir} --exclude "*/*" --include "{includePattern}"'
        print(f'run {awsCmd}')
        os.system(awsCmd)
        return datasetDir

