from rtCommon.projectInterface import processPyScriptRequest
from rtCommon.wsRequestStructs import resultStruct


class SubjectInterface:
    def sendClassificationResult(self, runId, trId, value):
        cmd = resultStruct(runId, trId, value)
        _ = processPyScriptRequest(cmd)

    def sendResultToWeb(self, runId, trId, value):
        self.sendClassificationResult(runId, trId, value)

