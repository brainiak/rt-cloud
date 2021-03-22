"""
A command-line service to be run where the where OpenNeuro data is downloaded and cached.
This service instantiates a BidsInterface object for serving the data back to the client
running in the cloud. It connects to the remote projectServer.
Once a connection is established it waits for requets and invokes the BidsInterface
functions to handle them.
"""
import os
import logging
import threading
#from rtCommon.bidsInterface import BidsInterface
from rtCommon.wsRemoteService import WsRemoteService, parseConnectionArgs
from rtCommon.utils import installLoggers

import boto3
import pandas as pd
from botocore.config import Config
from botocore import UNSIGNED
import toml
import shutil
import json

rootPath = "/tmp/openneuro/"
os.makedirs(rootPath, exist_ok = True)
'''
class OpenNeuroService:
    """
    A class that implements the OpenNeuroService by instantiating a BidsInterface, connecting
    to the remote projectServer and servicing requests to the BidsInterface.
    """
    def __init__(self, args, webSocketChannelName='wsData'):
        """
        Uses the WsRemoteService framework to parse connection-related args and establish
        a connection to a remote projectServer. Instantiates a local version of BidsInterface
        to handle client requests coming from the projectServer connection.
        Args:
            args: Argparse args related to connecting to the remote server. These include
                "-s <server>", "-u <username>", "-p <password>", "--test", 
                "-i <retry-connection-interval>"
            webSocketChannelName: The websocket url extension used to connecy and communicate
                to the remote projectServer, e.g. 'wsData' would connect to 'ws://server:port/wsData'
        """
        self.bidsInterface = BidsInterface(dataRemote=False)
        self.wsRemoteService = WsRemoteService(args, webSocketChannelName)
        self.wsRemoteService.addHandlerClass(BidsInterface, self.bidsInterface)

    def runDetached(self):
        """Starts the receiver in it's own thread."""
        self.recvThread = threading.Thread(name='recvThread',
                                           target=self.wsRemoteService.runForever)
        self.recvThread.setDaemon(True)
        self.recvThread.start()
'''
class OpenNeuroOverview(object):
    def __init__(self):
        self.archive_path = rootPath

    def get_dataset_list(self):
        """
        :return: a list of dataset available in OpenNeuro
        """
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        all_dataset = s3.list_objects(Bucket='openneuro.org', Delimiter="/")
        dataset_list = []
        for dataset in all_dataset.get('CommonPrefixes'):
            dataset_list.append(dataset.get('Prefix'))
        return dataset_list

    def display_description(self, accession_number):
        """
        read the dataset_description.json file
        :param accession_number: the dataset id
        :return: dataframe
        """
        object = accession_number + "/"
        if object not in self.get_dataset_list():
            print("dataset cannot be found in the OpenNeuro dataset.")
            return False
        else:
            path_to_file = accession_number + '/dataset_description.json'
            s3 = boto3.resource("s3", config=Config(signature_version=UNSIGNED))
            data_description = s3.Object('openneuro.org', path_to_file).get()['Body']
            df = pd.read_json(data_description, orient='index')
            pd.set_option('display.max_rows', None)
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', None)
            pd.set_option('display.max_colwidth', -1)
            return df

    def display_readme(self, accession_number):
        """
        read the README file
        :param accession_number: dataset id
        :return: everything in readme
        """
        object = accession_number + "/"
        if object not in self.get_dataset_list():
            print("dataset cannot be found in the OpenNeuro dataset.")
            return False
        else:
            try:
                path_to_file = accession_number + '/README'
                s3 = boto3.resource("s3", config=Config(signature_version=UNSIGNED))
                readme = s3.Object('openneuro.org', path_to_file).get()['Body'].read()
                readme_print = str(readme, 'utf-8')
                # print(readme_print)
                return readme_print
            except:
                print("readme file does not exist.")
                return False

    def check_archive(self, accession_number):
        """
        :return: whether this dataset is in archive
        """
        existed_dataset = [f.path.split("/")[1] for f in os.scandir(self.archive_path) if f.is_dir()]
        print(existed_dataset)
        if accession_number in existed_dataset:
            return True
        else:
            return False

    def get_dataset(self, accession_number, download_all, subject_id=None):
        """
        Open the dataset. If the dataset is not in the archive, download the dataset
        :param accession_number: the dataset id
        :param subject_id: the subject number, e.g. "01"
        :return: True if dataset exists. False otherwise.
        """
        if self.check_archive(accession_number):
            path = self.archive_path + accession_number
            return path, os.path.join(path, 'open_neuro.toml'), 'dataset'
        else:
            object = accession_number + "/"
            if object in self.get_dataset_list():
                download = DownloadOpenNeuroDataset(accession_number)
                print(subject_id)
                if not download_all:
                    download.download_subject(True, subject_id)
                    path = self.archive_path + accession_number + "_sub" + subject_id
                    return path, os.path.join(path, 'open_neuro.toml'), "sub"
                else:
                    download.download_all()
                    path = self.archive_path + accession_number
                    return path, os.path.join(path, 'open_neuro.toml'), 'dataset'

            else:
                print("This dataset does not exist in the OpenNeuro database.")
                return False


class DownloadOpenNeuroDataset(object):
    def __init__(self, accession_number):
        self.accession_number = accession_number
        self.subject = None
        self.rootpath = rootPath
        self.default_destination = self.rootpath + self.accession_number

    def get_subject_list(self, accession_number):
        """
        read all files and subdirectory of this dataset
        :param accession_number: the dataset id
        :return: a list of file and subdirectory names of this dataset
        """
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        dataset_info = []
        prefix = accession_number + '/'
        dataset = s3.list_objects(Bucket='openneuro.org', Delimiter="/", Prefix=prefix)
        for info in dataset.get('CommonPrefixes'):
            dataset_info.append(info.get('Prefix'))
        return dataset_info

    def check_subject(self, subject: str = "01"):
        """
        check whether the subject folder exists
        :param subject: the subject id. e.g. "01" means "sub-01". The default subject id is 01
        :return: whether the subject directory exists
        """
        paths = self.get_subject_list(self.accession_number)
        if not paths:
            return False
        path = "" + self.accession_number + "/sub-" + subject + "/"
        print(path)
        if path in paths:
            return True
        else:
            return False

    def download_all(self, destination=None):
        """
        Download the whole dataset
        :param destination: String the path to download
        """
        if destination is None:
            destination = self.default_destination
        try:
            request = 'aws s3 sync --no-sign-request s3://openneuro.org/' + self.accession_number + " " + destination
            os.system(request)
            print("Successfully downloaded")
            self.write_conf()
            return True
        except:
            print("error occur")
            return False

    def download_subject(self, root_included: bool, subject_id: str = "01", destination=None):
        """
        Download every file in the root directory and the specified individual subject folder
        :param root_included: whether to include root files
        :param subject_id: the subject id. e.g. "01" means "sub-01"
        :param destination: the path to download
        """
        self.subject = subject_id
        if not self.check_subject(subject_id):
            print("The dataset or subject folder does not exists.")
            return False

        if destination is None:
            destination = self.default_destination + "_sub" + subject_id
            self.default_destination = destination
        try:
            if root_included:
                request = "aws s3 cp --no-sign-request s3://openneuro.org/" + self.accession_number + " " + destination \
                          + " --recursive --exclude \"*/*\" --include \"sub-" + subject_id + "/*\""
                os.system(request)
                print("Successfully downloaded subject" + subject_id + " with all root files.")
            else:
                request = "aws s3 cp --no-sign-request s3://openneuro.org/" + self.accession_number + " " + destination \
                          + " --recursive --exclude \"*\" --include \"sub-" + subject_id + "/*\""
                os.system(request)
                print("Successfully downloaded subject" + subject_id + " with all root files.")
            self.write_conf()
            return True
        except Exception as e:
            print(e)
            return False

    def reformat(self):
        """
        Reformat it to the dataset that we can directly use for streaming
        :return:
        """
        pass

    def write_conf(self):
        conf_root = os.path.dirname(os.getcwd())
        conf_template = conf_root + "/conf/open_neuro.toml"
        shutil.copy(conf_template, self.default_destination)

        conf = toml.load(self.default_destination + "/open_neuro.toml")
        # get title
        description_path = self.default_destination + "/dataset_description.json"
        with open(description_path) as f:
            dataset_description = json.load(f)
        conf['title'] = dataset_description['Name']

        # get subject Name and subjectNum
        if self.subject is None:
            list_subName = [f.path.split("/")[1] for f in os.scandir(self.default_destination) if f.is_dir()]
            list_subNum = []
            for x in list_subName:
                if x.startswith('sub'):
                    list_subNum.append(x.split("-")[1])
            conf['subjectName'] = list_subName
            conf['subject'] = list_subNum
            # get session number does't change for now. Change based on subject. Default = None
        else:
            conf['subjectName'] = "sub-" + self.subject
            conf['subject'] = self.subject
        # save the edited toml file
        output_file_name = self.default_destination + "/open_neuro.toml"
        with open(output_file_name, "w") as toml_file:
            toml.dump(conf, toml_file)
'''
if __name__ == "__main__":
    installLoggers(logging.INFO, logging.INFO, filename='logs/OpenNeuroService.log')
    # parse connection args
    connectionArgs = parseConnectionArgs()

    try:
        #openNeuroService = OpenNeuroService(connectionArgs)
        # Use this command to run the service and not return control
        openNeuroService.wsRemoteService.runForever()
        # Alternately use this command to start the service in a thread and
        #  return control to main.
        # openNeuroService.runDetached()
    except Exception as err:
        print(f'Exception: {err}')
'''