var refreshCount = 0
var startTime

var FeedbackStatus = {
  connected : false,
  doFeedback: false,
  error : "No Error",
  message : "Begin Message",
  val : 0,
}

// function randomNumber() {
//   FeedbackStatus.val = Math.random() * 100
//   console.log(FeedbackStatus.val)
// }

// setInterval(randomNumber, 1000)

function createWebSocket() {
  var wsProtocol = 'wss://'
  if (location.protocol == 'http:') {
      wsProtocol = 'ws://'
  }
  var wsSubjURL = wsProtocol + location.hostname + ':' + location.port + '/wsSubject'
  console.log(wsSubjURL)
  var webSocket = new WebSocket(wsSubjURL);
  webSocket.onopen = (openEvent) => {
    FeedbackStatus.connected = true
    console.log("WebSocket OPEN: ");
  };
  webSocket.onclose = (closeEvent) => {
    FeedbackStatus.connected = false
    console.log("WebSocket CLOSE: ");
  };
  webSocket.onerror = (errorEvent) => {
    FeedbackStatus.error = JSON.stringify(errorEvent, null, 4)
    console.log("WebSocket ERROR: " + JSON.stringify(errorEvent, null, 4));
  };
  webSocket.onmessage = (messageEvent) => {
    var wsMsg = messageEvent.data;
    var request = JSON.parse(wsMsg)
    var reqClass = request['class']
    var reqCmd = request['attribute']
    var reqArgs = request['args']
    console.log(reqClass + " " + reqCmd + " " + reqArgs)
    // TODO - enqueue and event here and trigger rtEvent
    var retVal = true
    var retCode = 200
    if (reqCmd == 'setResult') {
      var val = reqArgs[2]
      FeedbackStatus.doFeedback = true
      FeedbackStatus.val = val
      FeedbackStatus.message = "BrainState: " + FeedbackStatus.val
      let event = new CustomEvent("rtEvent");
      document.dispatchEvent(event);
    } else if (reqCmd == 'setMessage') {
      FeedbackStatus.doFeedback = false // display message instead
      FeedbackStatus.message = reqArgs[0]
      let event = new CustomEvent("rtEvent");
      document.dispatchEvent(event);
    } else {
      errStr = "Unknown message type: " + reqCmd
      FeedbackStatus.error = errStr
      console.log(errStr)
      retVal = errStr
      retCode = 400
    }
    // Send the response
    var response = request;
    delete response['data']
    delete response['args']
    delete response['kwargs']
    response['dataSerialization'] = 'json'
    response['data'] = btoa(JSON.stringify(retVal))
    response['status'] = retCode
    webSocket.send(JSON.stringify(response))
  };
  this.webSocket = webSocket
}
