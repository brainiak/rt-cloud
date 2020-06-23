% syntax: [offsetTime timeWaited timedOut] = waitForKeyboard(trigger,
%                                                     inputDevice,timeout)
%
% Waits until a specific response is detected (e.g., when waiting for the
% user or for a scanner pulse) with minimal fuss. Reports success and wait
% times.
%
% User must specify what response to wait for, the input device (-1 or
% blank for keyboard), and the maximum time to wait (in seconds). A warning
% will be presented if no response is received prior to the timeout value.
% Supply timeout as "inf" or leave empty if you don't want a timeout.
%
%
% DEPENDENCIES
%
% requires PsychToolbox and SuperPsychToolbox
%
%
% Written by J. Poppenk May 14, 2013 @ Princeton University


function [offsetTime timeWaited timedOut] = waitForKeyboard(trigger_keycode,inputDevice,timeout)

    % timeout check
    if ~exist('timeout','var') || isempty(timeout) || isnan(timeout)
        timeout = inf;
    end

 
    
    % check input device
    if ~exist('inputDevice','var') || isempty(inputDevice)
        inputDevice = findInputDevice([],'keyboard');
    end
    
    % run multiChoice
    %[success, ~, ~, timeWaited] = multiChoice(timeout,trigger,[],trigger,GetSecs,inputDevice);
    
    KbQueueCreate(inputDevice);
    KbQueueStart(inputDevice);
    %KbReleaseWait(inputDevice, duration-(GetSecs - onset));
    KbQueueFlush(inputDevice);
    
    % listen for a valid response
    while (GetSecs < timeout)
        [pressed, key_code, ~, ~, released_code] = KbQueueCheck(inputDevice);%-changed on linux
        %[keyIsDown, secs, key_code, ~] = KbCheck(inputDevice);
        % find and sort key presses that are captured by KbQueueCheck
        if any(key_code)
            pressed_keys = find(key_code);
            if any(pressed_keys == trigger_keycode)
                success = 1;
                break;
            end
        end
    end % polling duration
    
    KbQueueRelease(inputDevice);
    
    % report
    timedOut = ~success;
    if timedOut
        %timeWaited = timeout;
        disp('waitForKeyboard timeout')
    end
    offsetTime = GetSecs();
    
return
