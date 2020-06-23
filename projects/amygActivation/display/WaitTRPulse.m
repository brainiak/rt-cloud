function varargout = WaitTRPulse(TRIGGER_keycode, DEVICE, timeToWait)

recorded = false;
secs = -1;
loop_delay = .0005;
TIMEOUT = 0.050; % 50 ms waiting period for trigger
TRlength = 1.5;
if ~exist('timeToWait', 'var')
    timeToWait = inf;
end
if ~exist('DEVICE', 'var')
    DEVICE = -1;
end
timeToWait = timeToWait + TIMEOUT;
while (GetSecs<timeToWait)
    WaitSecs(loop_delay);
    if timeToWait < inf % if set a time, make sure it's within 1 TR
        if GetSecs > timeToWait - (TRlength - TRlength/2) %only look if within a TR
            [keyIsDown,secs,keyCode] = KbCheck(DEVICE);
            if keyIsDown && any(ismember(TRIGGER_keycode,find(keyCode)))
                recorded = true;
                break;
            end
        end
    else % if haven't set a time, just wait until the trigger is pressed
        [keyIsDown,secs,keyCode] = KbCheck(DEVICE);
        if keyIsDown && any(ismember(TRIGGER_keycode,find(keyCode)))
            recorded = true;
            break;
        end
    end
end
varargout{1} = secs;
varargout{2} = recorded;
% if recorded
%     fprintf('|')
% else
%     fprintf('X')
% end
end