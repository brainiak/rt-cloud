"""
An example remote interface. Copy this file as a starting point for a new service.

Remote interfaces can be easily created by subclassing the RemoteExtensible class.

All methods in the subclass will be callable through an RPC interface which
the experiment script, running in the cloud, can access through the client object.

In addition to creating a subclassed RemoteExtensible, this class (object) must be instantiated
within the projectServerRPC class, e.g. exposed_ExampleInterface. The instantiated object
is what will be invoked when RPC calls are made to the exampleInterface.

For the remote case, there must be a remote end-point to handle the request. This can be within
a service (such as scannerDataService) that instantiates the classes (such as dataInterface,
bidsInterface, exampleInterface etc.) that will handle the remote forwarded requests.
Add the object to a data service, or create a new one, that will run at the control room
computer and is initialized with dataRemote=False.

The control room instance will be the actual instance and the projectServerRPC instance is
a stub instance (dataRemote=True) that forwards request to the control room instance.
"""
from rtCommon.remoteable import RemoteableExtensible


class ExampleInterface(RemoteableExtensible):
    """
    Provides functions for experimenter scripts
    """
    def __init__(self, dataRemote=False):
        """
        Args:
            dataRemote (bool): Set to true for the stub instance that will forward requests.
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

    def testMethod(self, *args, **kwargs):
        print(f'received args: {args}, kwargs: {kwargs}')
        res = [args, kwargs]
        return res
