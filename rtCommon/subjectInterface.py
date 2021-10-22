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
from rtCommon.errors import ValidationError


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
        self.message = ""

    # NOTE: The below function implementations will only be used when there is no
    #  external subjectInterface connected to the projectServer. Thus these
    #  implementations are just for testing or as a place holder when no external
    #  subjectInterface is used.

    def setResult(self, runId :int, trId :int, value: float, onsetTimeDelayMs: int=0) -> None:
        """
        When setResult is called by the experiment script it queues the result for
        the presentation script to later read and use to provide subject feedback.
        Args:
            runId: experiment specific identifier of the run
            trId: volume number of the dicom within a run
            value: the classification result from processing the dicom image for this TR
            onsetTimeDelayMs: time in milliseconds to wait before presenting the feedback stimulus
        """
        print(f'SubjectInterface: setResult: run {runId}, tr {trId}, value {value}')
        if onsetTimeDelayMs < 0:
            raise ValidationError(f'onsetTimeDelayMs must be >= 0, {onsetTimeDelayMs}')

        feedbackMsg = {
            'runId': runId,
            'trId': trId,
            'value': value,
            'onsetTimeDelayMs': onsetTimeDelayMs,
            'timestamp': time.time()
        }
        self.msgQueue.put(feedbackMsg)

    def setMessage(self, message: str) -> None:
        """
        Updates the message displayed to the subject
        """
        print(f'SubjectInterface: setMessage: {message}')
        self.message = message

    def getResponse(self, runId :int, trId :int):
        """
        Retrieve the subject response, used by the classification script.
        See *note* above - these local versions of the function are just
        for testing or as a place holder when no external subjectInterface
        is used.
        """
        print(f'SubjectInterface: getResponse: run {runId}, tr {trId}')
        return {}

    def getAllResponses(self):
        """
        Retrieve all subject responses since the last time this call was made
        """
        print(f'SubjectInterface: getAllResponses')
        return [{}]

    def dequeueResult(self, block :bool=False, timeout :int=None) -> float:
        """
        Return the next result value sent by the experiment script. Used by the
        presentation script.
        See *note* above - these local versions of the function are just
        for testing or as a place holder when no external version is used.
        """
        return self.msgQueue.get(block=block, timeout=timeout)


