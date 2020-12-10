import json
import numbers
from rtCommon.webSocketHandlers import sendWebSocketMessage
from rtCommon.errors import RequestError

class WebDisplayInterface:
    def __init__(self, ioLoopInst=None):
        self.ioLoopInst = ioLoopInst
        # dataPoints is a list of lists, each inner list is the points for a runId of that index
        self.dataPoints = [[{'x': 0, 'y': 0}]]

    def userLog(self, logStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'userLog', 'value': logStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("UserLog: " + logStr)

    def sessionLog(self, logStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'sessionLog', 'value': logStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("SessionLog: " + logStr)

    def debugLog(self, logStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'debugLog', 'value': logStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("DebugLog: " + logStr)

    def setUserError(self, errStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'userError', 'error': errStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("UseError: " + errStr)

    def setDebugError(self, errStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'debugError', 'error': errStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("DebugError: " + errStr)

    def sendRunStatus(self, statusStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'runStatus', 'status': statusStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("RunStatus: " + statusStr)

    def sendUploadStatus(self, fileStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'uploadStatus', 'file': fileStr}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("UploadStatus: " + fileStr)

    def sendConfig(self, config, filename=''):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'setConfig', 'value': config, 'filename': filename}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("sendConfig: " + filename)

    def sendPreviousDataPoints(self):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'setDataPoints', 'value': self.dataPoints}
            self._sendMessageToWeb(json.dumps(cmd))
        else:
            print("sendPreviousDataPoints: " + self.dataPoints)

    def plotDataPoint(self, runId, trId, value):
        msg = {
            'cmd': 'plotDataPoint',
            'runId': runId,
            'trId': trId,
            'value': value,
        }
        self._addResultValue(runId, trId, value)
        if self.ioLoopInst is not None:
            self._sendMessageToWeb(msg)
        else:
            print(f"plotDataPoint: run {runId}, tr {trId}, value {value}")

    def clearAllPlots(self):
        self.dataPoints = [[{'x': 0, 'y': 0}]]
        self.sendPreviousDataPoints()

    def clearRunPlot(self, runId):
        self.plotDataPoint(runId, None, None)

    def getPreviousDataPoints(self):
        return self.dataPoints

    def _addResultValue(self, runId, trId, value):
        """Track classification result values, used to plot the results in the web browser."""
        # This assume runIds starting at 1 (not zero based)
        if not isinstance(runId, numbers.Number) or runId <= 0:
            raise RequestError(f'addResultValue: runId must be number > 0: {runId}')
        x = trId
        y = value
        # Make sure dataPoints has at least as many arrays as runIds
        for i in range(len(self.dataPoints), runId):
            self.dataPoints.append([])
        if not isinstance(x, numbers.Number):
            # clear plot for this runId
            self.dataPoints[runId-1] = []
            return
        runVals = self.dataPoints[runId-1]
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
