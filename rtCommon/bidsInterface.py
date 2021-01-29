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
import time
from rtCommon.remoteable import RemoteableExtensible


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

    # Example function
    def echo(self, val):
        msg = f"Echo: {val}"
        print(msg)
        return msg
