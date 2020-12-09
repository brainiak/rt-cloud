import json
import numbers
from rtCommon.webSocketHandlers import sendWebSocketMessage
from rtCommon.errors import RequestError

class WebDisplayInterface:
    def __init__(self, ioLoopInst=None):
        self.ioLoopInst = ioLoopInst
        self.resultVals = [[{'x': 0, 'y': 0}]]

    def setIoLoopInst(self, ioLoopInst):
        self.ioLoopInst = ioLoopInst

    def userLog(self, logStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'userLog', 'value': logStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("UserLog: " + logStr)

    def setUserError(self, errStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'error', 'error': errStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("UseError: " + errStr)

    def debugLog(self, logStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'debugLog', 'value': logStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("DebugLog: " + logStr)

    def debugError(self, errStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'debugErr', 'error': errStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("DebugError: " + errStr)

    def sessionLog(self, logStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'sessionLog', 'value': logStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("SessionLog: " + logStr)

    def sendRunStatus(self, statusStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'runStatus', 'status': statusStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("RunStatus: " + statusStr)

    def sendUploadStatus(self, fileStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'uploadProgress', 'file': fileStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("UploadStatus: " + fileStr)

    def sendUserConfig(self, config, filename=''):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'config', 'value': config, 'filename': filename}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("sendConfig: " + filename)

    def sendUserDataVals(self, dataPoints):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'dataPoints', 'value': dataPoints}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("sendDataVals: " + dataPoints)

    def graphResult(self, runId, trId, value):
        msg = {
            'cmd': 'resultValue',
            'runId': runId,
            'trId': trId,
            'value': value,
        }
        self._addResultValue(runId, trId, value)
        if self.ioLoopInst is not None:
            self._sendMessageToWeb(msg)

    def getResultValues(self):
        return self.resultVals

    def clearResultValues(self):
        self.resultVals = [[{'x': 0, 'y': 0}]]

    def _addResultValue(self, runId, trId, value):
        """Track classification result values, used to plot the results in the web browser."""
        # This assume runIds starting at 1 (not zero based)
        if not isinstance(runId, numbers.Number) or runId <= 0:
            raise RequestError(f'addResultValue: runId must be number > 0: {runId}')
        x = trId
        y = value
        # Make sure resultVals has at least as many arrays as runIds
        for i in range(len(self.resultVals), runId):
            self.resultVals.append([])
        if not isinstance(x, numbers.Number):
            # clear plot for this runId
            self.resultVals[runId-1] = []
            return
        runVals = self.resultVals[runId-1]
        for i, val in enumerate(runVals):
            if val['x'] == x:
                runVals[i] = {'x': x, 'y': y}
                return
        runVals.append({'x': x, 'y': y})    

    def _sendMessageToWeb(self, msg):
        if self.ioLoopInst is not None:
            self.ioLoopInst.add_callback(sendWebSocketMessage, wsName='wsUser', msg=msg)
        else:
            print(f'WebDisplayMsg {msg}')
