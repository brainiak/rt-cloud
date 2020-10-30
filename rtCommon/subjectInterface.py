from rtCommon.webServer import processPyScriptRequest
from rtCommon.wsRequestStructs import resultStruct


class SubjectInterface:
    def __init__(self, detached=False):
        self.detached = detached

    def sendClassificationResult(self, runId, trId, value):
        cmd = resultStruct(runId, trId, value)
        if not self.detached:
            _ = processPyScriptRequest(cmd)
        else:
            print(f'SubjectInterface: run {runId}, tr {trId}, value {value}')

    def sendResultToWeb(self, runId, trId, value):
        self.sendClassificationResult(runId, trId, value)

