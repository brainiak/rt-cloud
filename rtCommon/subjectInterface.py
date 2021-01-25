"""
SubjectInterface is a client interface (i.e. for the experiment script running in the cloud)
that facilitates interaction with the subject in the MRI scanner, such as sending
classification results to drive the subject display, or receiving their responses (e.g. button-box).

To support RPC calls from the client, there will be two instances of SubjectInterface, one
at the cloud projectServer which is a stub to forward requests (started with subjectRemote=True),
and another at the presentation computer, run as a service and with subjectRemote=False.

The subjectInterface instance can also be instantiated within the projectServer if the
projectServer and presentation computer run on the same system.
"""
import time
from queue import Queue, Empty
from rtCommon.remoteable import RemoteableExtensible


class SubjectInterface(RemoteableExtensible):
    """
    Provides functions for sending feedback and receiving reponses from the subject in the scanner.

    If subjectRemote=True, then the RemoteExtensible parent class takes over and forwards all
    requests to a remote server via a callback function registered with the RemoteExtensible object.
    In that case *none* of the methods below will be locally invoked.

    If subjectRemote=False, then the methods below will be invoked locally and the RemoteExtensible
    parent class is inoperable (i.e. does nothing).

    When classification results are received from the experiment script they are placed in a
    queue which the presentation script can then access. The presentation script can wait
    on the queue for new results to arrive.
    """
    def __init__(self, subjectRemote=False):
        """
        Args:
            subjectRemote (bool): whether this instance is running on the presentation computer
                (subjectRemote=False) or running on the projectServer and forwarding subject
                requests via RPC (subjectRemote=True)
        """
        super().__init__(isRemote=subjectRemote)
        if subjectRemote is True:
            return
        self.msgQueue = Queue()

    def setResult(self, runId :int, trId :int, value: float) -> None:
        """
        Whe setResult is called by the experiment script it queues the result for
        the presentation script to later read and use to provide subject feedback.
        Args:
            runId: experiment specific identifier of the run
            trId: volume number of the dicom within a run
            value: the classification result from processing the dicom image for this TR
        """
        print(f'SubjectInterface: setResult: run {runId}, tr {trId}, value {value}')
        feedbackMsg = {
            'runId': runId,
            'trId': trId,
            'value': value,
            'timestamp': time.time()
        }
        self.msgQueue.put(feedbackMsg)

    def dequeueResult(self, block :bool=False, timeout :int=None) -> float:
        """
        Return the next result value send by the experiment script. Used by the
        presentation script.
        """
        return self.msgQueue.get(block=block, timeout=timeout)

    def getResponse(self, runId :int, trId :int):
        """
        Retrieve the subject response, used by the classification script.
        """
        print(f'SubjectInterface: getResponse: run {runId}, tr {trId}')
        pass
