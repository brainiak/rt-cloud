import pytest
import json
import websocket
from tests.backgroundTestServers import BackgroundTestServers
from rtCommon.clientInterface import ClientInterface
from rtCommon.structDict import StructDict
from rtCommon.projectUtils import login
from tests.common import testPort


class TestWebInterface:
    serversForTests = None

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()
        cls.serversForTests.startServers(subjectRemote=False, dataRemote=False)

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    def test_webBrowserRequests(self):
        ws = connectWebClient()
        assert ws.connected is True

        # test outgoing commands
        cmd = {'cmd': 'getDefaultConfig'}
        vals = runCmd(ws, cmd)

        # set default config value
        cfg = vals.get('value')

        cfg['runNum'] = [1]
        cmd = {'cmd': 'runScript', 'args': ['mainScript'], 'config': cfg}
        runCmd(ws, cmd)

        cmd = {'cmd': 'getDataPoints'}
        runCmd(ws, cmd)

        cmd = {'cmd': 'clearDataPoints'}
        runCmd(ws, cmd)

        cmd = {'cmd': 'stop'}
        runCmd(ws, cmd)
        ws.close()

    def test_webServerRequests(self):
        # Make a connection from the web browser side
        ws = connectWebClient()
        assert ws.connected is True
        # Get script side connection to webBrowser
        clientInterface = ClientInterface()
        webInterface = clientInterface.webInterface

        webInterface.userLog('Test user log')
        expectWebResult(ws, 'userLog', 'value', 'Test user log')

        webInterface.sessionLog('Test session log')
        expectWebResult(ws, 'sessionLog', 'value', 'Test session log')

        webInterface.debugLog('Test debug log')
        expectWebResult(ws, 'debugLog', 'value', 'Test debug log')

        webInterface.setUserError('Set user error')
        expectWebResult(ws, 'userError', 'error', 'Set user error')

        webInterface.setDebugError('Set debug error')
        expectWebResult(ws, 'debugError', 'error', 'Set debug error')

        webInterface.sendRunStatus('Set run status')
        expectWebResult(ws, 'runStatus', 'status', 'Set run status')

        webInterface.sendUploadStatus('filename1')
        expectWebResult(ws, 'uploadStatus', 'file', 'filename1')

        emptyPoints = [[{'x': 0, 'y': 0}]]
        webInterface.sendPreviousDataPoints()
        expectWebResult(ws, 'setDataPoints', 'value', emptyPoints)

        webInterface.plotDataPoint(1, 2, 3)
        expectWebResult(ws, 'plotDataPoint', 'runId', 1)

        dataPoints = [[{'x': 0, 'y': 0}, {'x': 2, 'y': 3}]]
        webInterface.sendPreviousDataPoints()
        expectWebResult(ws, 'setDataPoints', 'value', dataPoints)

        testCfg = {'val1': 'a', 'val2': 'b'}  # dict(val = 'test')
        webInterface.sendConfig(testCfg, 'testfile')
        expectWebResult(ws, 'setConfig', 'value', testCfg)


def expectWebResult(ws, cmdName, key, value):
    jres = ws.recv()
    res = json.loads(jres)
    # print(res)
    assert res.get('cmd') == cmdName
    assert res.get(key) == value


def runCmd(ws, cmd):
    jcmd = json.dumps(cmd)
    ws.send(jcmd)
    result = ws.recv()
    vals = json.loads(result)
    # print(vals)
    assert vals.get('error') is None
    return vals


def connectWebClient():
    sessionCookie = login(f'localhost:{testPort}', 'test', 'test', testMode=True)
    ws = websocket.WebSocket()
    ws.connect(f'ws://localhost:{testPort}/wsUser', cookie="login="+sessionCookie)
    return ws
