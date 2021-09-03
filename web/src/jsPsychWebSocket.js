var refreshCount = 0;
var startTime;

// Store the incoming feedback (i.e. classification results)
var FeedbackStatus = {
  connected : false,
  doFeedback: false,
  error : "No Error",
  message : "Begin Message",
  runId : 0,
  trId : 0,
  val : 0,
};

// Collect the subject's keyboard responses
var ResponseQueue = [];

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
    var retVal = true
    var retCode = 200
    if (reqCmd == 'setResult') {
      var runId = reqArgs[0]
      var trId = reqArgs[1]
      var val = reqArgs[2]
      var msTimeDelay = reqArgs[3]
      FeedbackStatus.doFeedback = true
      FeedbackStatus.runId = runId
      FeedbackStatus.trId = trId
      FeedbackStatus.val = val
      FeedbackStatus.message = "BrainState: " + FeedbackStatus.val
      // Trigger the rtEvent to end the previous trial and start this next one
      let event = new CustomEvent("rtEvent", {detail: {msTimeDelay: msTimeDelay}});
      document.dispatchEvent(event);
    } else if (reqCmd == 'setMessage') {
      FeedbackStatus.doFeedback = false // display message instead
      FeedbackStatus.message = reqArgs[0]
      let event = new CustomEvent("rtEvent", {detail: {msTimeDelay: 0}});
      document.dispatchEvent(event);
    } else if (reqCmd = 'getResponses') {
      // Dequeue and return all data from ResponseQueue
      retVal = []
      while (ResponseQueue.length > 0) {
        var entry = ResponseQueue.shift();
        retVal.push(entry);
      }
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
