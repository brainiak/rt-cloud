"""
Client module for sending feedback (from classification results) to the subject in the MRI scanner.
And for receiving their manual responses (i.e. button box or other) to that feedback.
"""
from rtCommon.webServer import processPyScriptRequest
from rtCommon.wsRequestStructs import resultStruct


class SubjectInterface:
    """Provides functions for sending feedback and receiving reponses from the subject in the scanner."""
    def __init__(self, detached=False):
        self.detached = detached

    def sendClassificationResult(self, runId, trId, value):
        """Send classification results the a feedbackReceiver, such as running with psychoPy."""
        cmd = resultStruct(runId, trId, value)
        if not self.detached:
            _ = processPyScriptRequest(cmd)
        else:
            print(f'SubjectInterface: run {runId}, tr {trId}, value {value}')

    def sendResultToWeb(self, runId, trId, value):
        """Send classification results to the web interface for graphing or logging."""
        self.sendClassificationResult(runId, trId, value)

