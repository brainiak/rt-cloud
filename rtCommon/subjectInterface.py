"""
Client module for sending feedback (from classification results) to the subject in the MRI scanner.
And for receiving their manual responses (i.e. button box or other) to that feedback.
"""
import time
from queue import Queue, Empty
from rtCommon.remoteable import RemoteableExtensible


class SubjectInterface(RemoteableExtensible):
    """
    Provides functions for sending feedback and receiving reponses from the subject in the scanner.
    """
    def __init__(self, dataremote=False):
        super().__init__(dataremote)
        if dataremote is True:
            return
        self.msgQueue = Queue()
    
    def setResult(self, runId, trId, value):
        print(f'SubjectInterface: setResult: run {runId}, tr {trId}, value {value}')
        feedbackMsg = {
            'runId': runId,
            'trId': trId,
            'value': value,
            'timestamp': time.time()
        }
        self.msgQueue.put(feedbackMsg)
        pass

    def getResponse(self, runId, trId):
        print(f'SubjectInterface: getResponse: run {runId}, tr {trId}')
        pass


# from rtCommon.webServer import processPyScriptRequest
# from rtCommon.wsRequestStructs import resultStruct


# class SubjectInterface:
#     """Provides functions for sending feedback and receiving reponses from the subject in the scanner."""
#     def __init__(self, dataremote=False):
#         self.dataremote = dataremote

#     def sendClassificationResult(self, runId, trId, value):
#         """Send classification results the a feedbackReceiver, such as running with psychoPy."""
#         cmd = resultStruct(runId, trId, value)
#         if not self.dataremote:
#             _ = processPyScriptRequest(cmd)
#         else:
#             print(f'SubjectInterface: run {runId}, tr {trId}, value {value}')

#     def sendResultToWeb(self, runId, trId, value):
#         """Send classification results to the web interface for graphing or logging."""
#         self.sendClassificationResult(runId, trId, value)

# # helper function for creating remote subject request
# def resultStruct(runId, trId, value):
#     cmd = {'cmd': 'resultValue',
#            'runId': runId,
#            'trId': trId,
#            'value': value,
#            }
#     return cmd