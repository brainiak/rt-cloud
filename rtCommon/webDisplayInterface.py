"""
WebDisplayInterface is a client interface (i.e. for the experiment script running in the cloud) 
that provides calls that affect what is displayed in the users web browser. It is also used
internally within projectServer for setting log and error messages within the web browser.
"""
import json
import numbers
from rtCommon.projectUtils import npToPy
from rtCommon.webSocketHandlers import sendWebSocketMessage
from rtCommon.errors import RequestError

class WebDisplayInterface:
    def __init__(self, ioLoopInst=None):
        """
        Args:
            ioLoopInst - Tornado webserver i/o event loop, for synchronizing websocket communication
        """
        self.ioLoopInst = ioLoopInst
        # dataPoints is a list of lists, each inner list is the points for a runId of that index
        self.dataPoints = [[{'x': 0, 'y': 0}]]

    def userLog(self, logStr):
        """Set a log message in the user log area of the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'userLog', 'value': logStr}
            self._sendMessageToWeb(cmd)
        else:
            print("UserLog: " + logStr)

    def sessionLog(self, logStr):
        """Set a log message in the session log area of the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'sessionLog', 'value': logStr}
            self._sendMessageToWeb(cmd)
        else:
            print("SessionLog: " + logStr)

    def debugLog(self, logStr):
        """Set a log message in the debug log area of the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'debugLog', 'value': logStr}
            self._sendMessageToWeb(cmd)
        else:
            print("DebugLog: " + logStr)

    def setUserError(self, errStr):
        """Set an error message in the error display area of the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'userError', 'error': errStr}
            self._sendMessageToWeb(cmd)
        else:
            print("UseError: " + errStr)

    def setDebugError(self, errStr):
        """Set an error message in the debug display area of the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'debugError', 'error': errStr}
            self._sendMessageToWeb(cmd)
        else:
            print("DebugError: " + errStr)

    def sendRunStatus(self, statusStr):
        """Indicate run status in the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'runStatus', 'status': statusStr}
            self._sendMessageToWeb(cmd)
        else:
            print("RunStatus: " + statusStr)

    def sendUploadStatus(self, fileStr):
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'uploadStatus', 'file': fileStr}
            self._sendMessageToWeb(cmd)
        else:
            print("UploadStatus: " + fileStr)

    def sendConfig(self, config, filename=''):
        """Send the project configurations to the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'setConfig', 'value': config, 'filename': filename}
            self._sendMessageToWeb(cmd)
        else:
            print("sendConfig: " + filename)

    def sendPreviousDataPoints(self):
        """Send previously plotted data points to the web page"""
        if self.ioLoopInst is not None:
            cmd = {'cmd': 'setDataPoints', 'value': self.dataPoints}
            self._sendMessageToWeb(cmd)
        else:
            print("sendPreviousDataPoints: " + self.dataPoints)

    def plotDataPoint(self, runId, trId, value):
        """Add a new data point to the web page plots"""
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
        """Clear all data plots in the web page"""
        self.dataPoints = [[{'x': 0, 'y': 0}]]
        self.sendPreviousDataPoints()

    def clearRunPlot(self, runId):
        """Clear the data plot for the specfied run"""
        self.plotDataPoint(runId, None, None)

    def getPreviousDataPoints(self):
        """Local command to retrieve previously plotted points (doesn't send to web page)"""
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
        """Helper function used by the other methods to send a message to the web page"""
        if self.ioLoopInst is not None:
            msg = npToPy(msg)
            json_msg = json.dumps(msg)
            self.ioLoopInst.add_callback(sendWebSocketMessage, wsName='wsUser', msg=json_msg)
        else:
            print(f'WebDisplayMsg {msg}')
