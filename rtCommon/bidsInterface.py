"""
Examlpe interface, modify to add functionality
"""
import time
from rtCommon.remoteable import RemoteableExtensible


class BidsInterface(RemoteableExtensible):
    """
    Provides functions for experimenter scripts
    """
    def __init__(self, dataremote=False):
        super().__init__(dataremote)
        if dataremote is True:
            return
        # Other initialization here
    
    # Example function
    def echo(self, val):
        return f"Echo: {val}"
