"""
Examlpe interface, modify to add functionality
"""
import time
from rtCommon.remoteable import RemoteableExtensible


class BidsInterface(RemoteableExtensible):
    """
    Provides functions for experimenter scripts
    """
    def __init__(self, dataRemote=False):
        super().__init__(isRemote=dataRemote)
        if dataRemote is True:
            return
        # Other initialization here

    # Example function
    def echo(self, val):
        msg = f"Echo: {val}"
        print(msg)
        return msg