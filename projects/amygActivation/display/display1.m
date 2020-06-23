% Display for Green Eyes sample experiment where we just want the subject
% to listen to the story!
% load necessary scanner settings

% wait 5 TR's before starting story?
debug=1;
useButtonBox=0;
CONTEXT=1; 
addpath(genpath('stimuli'))
% CONTEXT:
% 0 = NEITHER
% 1 = PARANOID
% 2 = CHEATING
% load in audio data and specify where the project is located
basic_path = '/Volumes/norman/amennen/RT_prettymouth/';
wavfilename = [basic_path '/stimuli/greenMyeyes_Edited.wav'];
%% Initalizing scanner parameters

disdaqs = 15; % how many seconds to drop at the beginning of the run
TR = 1.5; % seconds per volume

KbName('UnifyKeyNames');
if (~debug) %so that when debugging you can do other things
    %Screen('Preference', 'SkipSyncTests', 1);
   ListenChar(2);  %prevent command window output
   HideCursor;     %hide mouse cursor  
   
else
    Screen('Preference', 'SkipSyncTests', 2);
end
%initialize system time calls
seed = sum(100*clock); %get random seed
GetSecs;

% display parameters
textColor = 0;
textFont = 'Arial';
textSize = 35;
textSpacing = 25;
fixColor = 0;
backColor = 127;
fixationSize = 4;% pixels
minimumDisplay = 0.25;
LEFT = KbName('1!');
subj_keycode = LEFT;
DEVICENAME = 'Current Designs, Inc. 932';
if useButtonBox && (~debug)
    [index devName] = GetKeyboardIndices;
    for device = 1:length(index)
        if strcmp(devName(device),DEVICENAME)
            DEVICE = index(device);
        end
    end
else
    DEVICE = -1;
end
%TRIGGER = '5%';
TRIGGER ='=+'; %put in for Princeton scanner
TRIGGER_keycode = KbName(TRIGGER);

%% Initialize Screens

screenNumbers = Screen('Screens');

% show full screen if real, otherwise part of screen
if debug
    screenNum = 0;
else
    screenNum = screenNumbers(end);
end

%retrieve the size of the display screen
if debug
    screenX = 800;
    screenY = 800;
else
    % first just make the screen tiny
    
    [screenX screenY] = Screen('WindowSize',screenNum);
    % put this back in!!!
    windowSize.degrees = [51 30];
    resolution = Screen('Resolution', screenNum);
    %resolution = Screen('Resolution', 0); % REMOVE THIS AFTERWARDS!!
    %windowSize.pixels = [resolution.width/2 resolution.height];
    %screenX = windowSize.pixels(1);
    %screenY = windowSize.pixels(2);
    % new: setting resolution manually
     screenX = 1920;
     screenY = 1080;
%     %to ensure that the images are standardized (they take up the same degrees of the visual field) for all subjects
%     if (screenX ~= ScreenResX) || (screenY ~= ScreenResY)
%         fprintf('The screen dimensions may be incorrect. For screenNum = %d,screenX = %d (not 1152) and screenY = %d (not 864)',screenNum, screenX, screenY);
%     end
end

%create main window
% ACM: took out if statement because specifying top doesn't work on penn
% comp
%if (useButtonBox)%scanner display monitor has error with inputs of screen size
%    mainWindow = Screen(screenNum,'OpenWindow',backColor);
%else
mainWindow = Screen(screenNum,'OpenWindow',backColor,[0 0 screenX screenY]);
%end
ifi = Screen('GetFlipInterval', mainWindow);
slack  = ifi/2;
% details of main window
centerX = screenX/2; centerY = screenY/2;
Screen(mainWindow,'TextFont',textFont);
Screen(mainWindow,'TextSize',textSize);
fixDotRect = [centerX-fixationSize,centerY-fixationSize,centerX+fixationSize,centerY+fixationSize];
%% check audio volume in the scanner

% preview task
% check audio volume
InitializePsychSound(1)
nrchannels = 2;
okayVolume=0;
while ~okayVolume
    freq=44100;
    duration=1;
    snddata = MakeBeep(378, duration, freq);
    dualdata = [snddata;snddata];
    pahandle = PsychPortAudio('Open', [], [], [], freq, nrchannels);
    PsychPortAudio('FillBuffer', pahandle, dualdata);
    % start it immediately
    PsychPortAudio('UseSchedule',pahandle,1);
    PsychPortAudio('AddToSchedule',pahandle,0);
    trigger=GetSecs + 2;
    begin_time = PsychPortAudio('Start', pahandle, [], trigger);
    resp = input('Volume level okay? \n');
    if resp == 1
        okayVolume = 1;
    end
end
%Stop playback:
PsychPortAudio('Stop', pahandle);
% Close the audio device:
PsychPortAudio('Close', pahandle);

%% Load in audio data for story
%
[y, freq] = audioread(wavfilename);
wavedata = y';
nrchannels = size(wavedata,1); % Number of rows

%% show them instructions until they press to begin

% show instructions
Screen(mainWindow,'FillRect',backColor);
Screen('Flip',mainWindow);
FlushEvents('keyDown');

instructCell = getContext(CONTEXT);

% first give context for the story
for instruct=1:length(instructCell)
    tempBounds = Screen('TextBounds',mainWindow,instructCell{instruct});
    if instruct==length(instructCell)
        textSpacing = textSpacing*3;
    end
    Screen('drawtext',mainWindow,instructCell{instruct},centerX-tempBounds(3)/2,centerY-tempBounds(4)/5+textSpacing*(instruct-1),textColor);
    clear tempBounds;
end
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% now here we're adding to say waiting for scanner, hold tight!
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
waitMessage = 'Waiting for scanner start, hold tight!';
tempBounds = Screen('TextBounds', mainWindow, waitMessage);
Screen('drawtext',mainWindow,waitMessage,centerX-tempBounds(3)/2,centerY-tempBounds(4)/2,textColor);
Screen('Flip', mainWindow);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% now here we're going to say to stay still once the triggers start coming
% in
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
STILLREMINDER = ['The scan is now starting.\n\nMoving your head even a little blurs the image, so '...
    'please try to keep your head totally still until the scanning noise stops.\n\n Do it for science!'];
STILLDURATION = 6;

% wait for initial trigger
Priority(MaxPriority(screenNum));
%% Wait for first trigger in the scanner
if (~debug )
        timing.trig.wait = WaitTRPulse(TRIGGER_keycode,DEVICE);
        runStart = timing.trig.wait;
        DrawFormattedText(mainWindow,STILLREMINDER,'center','center',textColor,70)
        startTime = Screen('Flip',mainWindow);
        elapsedTime = 0;
        while (elapsedTime < STILLDURATION)
            pause(0.005)
            elapsedTime = GetSecs()-startTime;
        end
else
    runStart = GetSecs;
end
Screen(mainWindow,'FillRect',backColor);
Screen(mainWindow,'FillOval',fixColor,fixDotRect);
Screen('Flip',mainWindow);
Priority(0);

%%
pahandle = PsychPortAudio('Open', [], [], [], freq, nrchannels);
PsychPortAudio('FillBuffer', pahandle, wavedata);

% calculate onset of story
audioOnset = disdaqs;
volCounter = 1 + disdaqs/TR = 1;
timing.plannedOnsets.audioStart = audioOnset + runStart;
%PsychPortAudio('UseSchedule',pahandle,1); 
%PsychPortAudio('AddToSchedule',pahandle,0); 
% actual playing
before_start = GetSecs;
trigger=GetSecs + 2;

begin_time = PsychPortAudio('Start', pahandle, [], trigger+1,1);
fprintf('start\n')
after_start= GetSecs;
s = PsychPortAudio('GetStatus', pahandle);
disp(s)
fprintf('delay is %8.8f\n', trigger-begin_time)
%%
% Stop playback:
PsychPortAudio('Stop', pahandle);
% Close the audio device:
PsychPortAudio('Close', pahandle);
%% actual experiment: playing audio clip with feedback in between those segments
% just have the audio play from the wave file given
% let's wait 5 volumes and show the directions?
