/**
 * jspsych-brain-realtime-response
 * Sebastian Michelmann
 *
 * plugin for a trial that ends on an external 'rtEvent' event
*
 **/

jsPsych.plugins["brain-realtime-response"] = (function() {

  var plugin = {};

  // ideally the plugin should have a parameter that is reserved for an element that
  //   the listener should be attached to! (e.g. the websocket)
  plugin.info = {
    name: 'brain-realtime-response',
    description: '',
    parameters: {
      stimulus: {
        type: jsPsych.plugins.parameterType.FUNCTION,
        pretty_name: 'Stimulus',
        default: null,
        description: 'The drawing function to apply to the canvas. Should take the canvas object as argument.'
      },
      prompt: {
        type: jsPsych.plugins.parameterType.STRING,
        pretty_name: 'Prompt',
        default: null,
        description: 'Any content here will be displayed below the stimulus.'
      },
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
      }
    }
  }

  plugin.trial = function(display_element, trial) {

    // display stimulus
    //var html = '<div id="jspsych-html-button-response-stimulus">'+trial.stimulus+'</div>';

    var new_html = '<div id="jspsych-canvas-keyboard-response-stimulus" ' +
                      'height="' + trial.canvas_size[0] + '" ' +
                      'width="' + trial.canvas_size[1] + '" ' +
                    '>';


    if (trial.stimulus != null) {
      var canvas_html = '<canvas id="jspsych-canvas-stimulus" ' +
                          'height="' + trial.canvas_size[0] + '" ' +
                          'width="' + trial.canvas_size[1] + '" ' +
                        '></canvas>'
      new_html += canvas_html + '</div>'
    }
    // add prompt
    if (trial.prompt !== null) {
      new_html += '</div>' + trial.prompt;
    }

    display_element.innerHTML = new_html;

    if (trial.stimulus != null) {
      let canvas = document.getElementById("jspsych-canvas-stimulus")
      trial.stimulus(canvas)
    }

    // start time
    var start_time = performance.now();
    var rtEvent_time = null;

    // function to wrap up when the event has arrived (not finished if it's too early)
    function wrap_up(){
      // remove the listener first!
      document.removeEventListener('rtEvent', wrap_up);

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
      // gather the data to store for the trial
      var trial_data = {
        "rtEvent_time":  rtEvent_time
      //  "stimulus": html
      };

      // clear the display
      display_element.innerHTML = '';
      // clear all timeouts
      jsPsych.pluginAPI.clearAllTimeouts();
      // finish
      jsPsych.finishTrial(trial_data);
    };

    // add event listeners to document
    document.addEventListener('rtEvent', wrap_up);

  };

  return plugin;
})();
