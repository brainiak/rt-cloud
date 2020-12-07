import numbers
from rtCommon.webSocketHandlers import sendWebSocketMessage
from rtCommon.errors import RequestError

class WebDisplayInterface:
    def __init__(self):
        self.ioLoopInst = None
        self.resultVals = [[{'x': 0, 'y': 0}]]

    def setIoLoopInst(self, ioLoopInst):
        self.ioLoopInst = ioLoopInst

    def graphResult(self, runId, trId, value):
        msg = {
            'cmd': 'resultValue',
            'runId': runId,
            'trId': trId,
            'value': value,
        }
        self.addResultValue(runId, trId, value)
        self._sendMessageToWeb(msg)

    def getResultValues(self):
        return self.resultVals

    def clearResultValues(self):
        self.resultVals = [[{'x': 0, 'y': 0}]]

    def addResultValue(self, runId, trId, value):
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
