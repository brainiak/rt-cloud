/**
 * jspsych-brain-realtime-response
 * Sebastian Michelmann
 *
 * plugin for a trial that ends on an external 'rtEvent' event
*
 **/

jsPsych.plugins["brain-realtime-response"] = (function() {

  var plugin = {};

  // TODO (Improvement) ideally the plugin should have a parameter that is reserved for an element that
  //   the listener should be attached to! (e.g. the websocket)
  plugin.info = {
    name: 'brain-realtime-response',
    description: '',
    parameters: {
      trial_duration: {
        type: jsPsych.plugins.parameterType.INT,
        pretty_name: 'Trial duration',
        default: null,
        description: 'The minimal duration of the trial.'
      },
      canvas_size: {
        type: jsPsych.plugins.parameterType.INT,
        array: true,
        pretty_name: 'Canvas size',
        default: [500, 500],
        description: 'Array containing the height (first value) and width (second value) of the canvas element.'
      },
      choices: {
        type: jsPsych.plugins.parameterType.KEY,
        array: true,
        pretty_name: 'Choices',
        default: jsPsych.NO_KEYS,
        description: 'The keys the subject is allowed to press to respond to the stimulus.'
      },
    }
  }

  plugin.trial = function(display_element, trial) {
    var start_time = performance.now();
    var rtEvent_time = null;
    // store subject's keyboard response
    var response = {
      rt: null,   // response time
      key: null,  // key pressed
    };

    // add event listeners to document
    document.addEventListener('rtEvent', event_handler);

    // function to handle responses by the subject
    var after_response = function(info) {
      // only record the first response
      if (response.key == null) {
        response = info;
      }
    };

    // start the response listener
    var keyboardListener = null;
    if (trial.choices != jsPsych.NO_KEYS) {
      keyboardListener = jsPsych.pluginAPI.getKeyboardResponse({
        callback_function: after_response,
        valid_responses: trial.choices,
        rt_method: 'performance',
        persist: false,
        allow_held_key: false,
      });
    }

    // function to wrap up when the event has arrived (not finished if it's too early)
    function event_handler(){
      // remove the listener first!
      document.removeEventListener('rtEvent', event_handler);

      // store when the rtEvent event happened
      rtEvent_time = performance.now() - start_time;

      // if the setResult was early we want to sleep for a bit
      if ((trial.trial_duration !== null) && (rtEvent_time < trial.trial_duration)){
        jsPsych.pluginAPI.setTimeout(end_trial, (trial.trial_duration-rtEvent_time))
      } else{
        //otherwise we just end the trial now
        end_trial()
      }
    }

    // function to end trial when it is time
    function end_trial() {
      if (keyboardListener != null) {
        jsPsych.pluginAPI.cancelKeyboardResponse(keyboardListener)
      }

      // gather the data to store for the trial
      var trial_data = {
        "rtEvent_time":  rtEvent_time,
        "key_pressed": response.key,
        "key_response_time": response.rt,
      };

      // clear the display
      display_element.innerHTML = '';
      // clear all timeouts
      jsPsych.pluginAPI.clearAllTimeouts();
      // finish
      jsPsych.finishTrial(trial_data);
    };
  };

  return plugin;
})();
