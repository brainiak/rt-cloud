"""
Examlpe remote interface, modify to add functionality. Remote interfaces can be easily
created by subclassing the RemoteExtensible class.

All methods in the subclass will be callable through an RPC interface
which the classification script running in the cloud can access throug the client object.

In addition to creating a subclassed RemoteExtensible, an instance of this object must also
be added to the projectServerRPC.py file, such as exposed_bidsInterface. And a data service
must run at the control room computer that has an instance of this class with dataRemote=False.

The control room instance will be the actual instance and the projectServerRPC instance is
a shell instance (dataRemote=True) that forwards request to the control room instance.
"""
import threading
import time

from rtCommon.bidsStreamer import bidsStreamer
from rtCommon.remoteable import RemoteableExtensible

class websocketState:
    """A global static class (really a struct) for maintaining connection and callback information."""
    wsConnLock = threading.Lock()
    # map from wsName to list of connections, such as 'wsData': [conn1]
    wsConnectionLists = {}
    # map from wsName to callback function, such as 'wsData': dataCallback
    wsCallbacks = {}

class BidsInterface(RemoteableExtensible):
    """
    Provides functions for experimenter scripts
    """
    def __init__(self, dataRemote=False):
        """
        Args:
            dataRemote (bool): Set to true for the shell instance that will forward requests.
                               Set to false for the actual instance running remotely
        """
        super().__init__(isRemote=dataRemote)
        if dataRemote is True:
            return
        # Other initialization here
        self.newStreamId = 0
        self.streamDict = {}
        self.streamInfo = {}
        self.rootPath ='/Users/cocozhao/Documents/GitHub/rt-cloud/projects/OpenNeuroClient/'# Todo: change pass to the cloud path
    # Example function
    def echo(self, val):
        msg = f"Echo: {val}"
        print(msg)
        return msg

    def init_bids_stream(self,datasetName, required_metadata, type:str, index:int = -1,path = None):
        if path is not None:
            self.rootPath = path
        websocketState.wsConnLock.acquire()
        try:
            self.newStreamId = self.newStreamId + 1
            self.streamDict[self.newStreamId] = bidsStreamer(datasetName, required_metadata, type, index, self.rootPath)
            return self.newStreamId
        finally:
            websocketState.wsConnLock.release()

    def get_next_img(self,streamId: int,imageIndex: int=None):
        streamer = self.streamDict[streamId]
        if streamer is None:
            return "error"
        if imageIndex != None:
            image = streamer.get_next_image(imageIndex)
        else:
            image = streamer.get_next_image()
        if image is None:
            return "image is none"
        return image
