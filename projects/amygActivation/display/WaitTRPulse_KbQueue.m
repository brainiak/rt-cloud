function varargout = WaitTRPulse_KbQueue(TRIGGER_keycode, DEVICE, timeToWait)
trig_map = zeros(1,256);
trig_map(TRIGGER_keycode) = 1;
LEFT = KbName('1!');
RIGHT = KbName('2@');
probe_keys = [LEFT RIGHT];

%KbQueueCreate(DEVICE,key_map);
%KbQueueStart(DEVICE);
%KbQueueFlush(DEVICE);
recorded = false;
secs = -1;
keyCode = NaN(1,256);
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
firstLoop = 1;
rt_LEFT = NaN;
rt_RIGHT = NaN;
recheck=1;

while (GetSecs<timeToWait)
    WaitSecs('Yieldsecs', 0.001);
    if timeToWait < inf % if set a time, make sure it's within 1 TR
        if GetSecs > timeToWait - (TRlength - TRlength/2) %only look if within a TR
%             if firstLoop
%                 [keyIsDown, keyCode] = KbQueueCheck(DEVICE);
%                 if keyCode(LEFT) || keyCode(RIGHT)
%                     
%                     if keyCode(LEFT)
%                         rt_LEFT = keyCode(LEFT);
%                     end
%                     if keyCode(RIGHT)
%                         rt_RIGHT = keyCode(RIGHT);
%                     end
%                     recheck = 0;
%                 end
%                 KbQueueFlush(DEVICE); % flush all key strokes in case you get to this too early
%                 firstLoop = 0;
            %end
            [keyIsDown, keyCode] = KbQueueCheck(DEVICE);
            if keyIsDown
                if keyCode(LEFT)
                    rt_LEFT = keyCode(LEFT);
                end
                %fprintf('L')
                %keyCode(LEFT)
                if keyCode(RIGHT)
                    rt_RIGHT = keyCode(RIGHT);
                end
                %fprintf('R')
                %keyCode(RIGHT)
            end
            if keyIsDown && keyCode(TRIGGER_keycode) > timeToWait - (TRlength - TRlength/2)
                recorded = true;
                break;
            end
        end
    else % if haven't set a time, just wait until the trigger is pressed
        [keyIsDown, keyCode] = KbQueueCheck(DEVICE);
        if keyIsDown && any(ismember(TRIGGER_keycode,find(keyCode)))
            recorded = true;
            break;
        end
    end
end
varargout{1} = keyCode(TRIGGER_keycode);
varargout{2} = recorded;
varargout{3} = rt_LEFT;
varargout{4} = rt_RIGHT;
%KbQueueFlush(DEVICE);
% if recorded
%     fprintf('|')
% else
%     fprintf('X')
% end
end