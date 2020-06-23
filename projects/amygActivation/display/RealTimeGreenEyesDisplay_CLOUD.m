% Display for Green Eyes sample experiment where we just want the subject
% to listen to the story!
% load necessary scanner settings

% wait 5 TR's before starting story?
% TO DO: % RANDOMIZE WHICH  SIZE CHEATING/PARANOID SIDE IS FOR EACH PERSON!
function RealTimeGreenEyesDisplay_CLOUD(toml_file, runNum)

% LOAD CONFIG FILE %
%toml_file = '/Data1/code/rt-cloud/projects/greenEyes/conf/greenEyes_organized.toml';
%toml_file = '/Volumes/norman/amennen/github/brainiak/rt-cloud/projects/greenEyes/conf/greenEyes_cluster.toml';
%runNum = 1;

addpath(genpath('matlab-toml'));
raw_text = fileread(toml_file);
cfg = toml.decode(raw_text);
runData.subjectNum = cfg.subjectNum;
runData.subjectName = cfg.subjectName;
runData.subjectDay = cfg.subjectDay;
runData.run = runNum;

debug = cfg.display.debug;
useButtonBox = cfg.display.useButtonBox;
if strcmp(cfg.machine, 'intel')
    fmri = 1;
else
    fmri = 0;
end
rtData = cfg.display.rtData;
usepython = cfg.display.usePython;

bidsId = sprintf('sub-%03d',runData.subjectNum);
runId = sprintf('run-%03d',runData.run);
addpath(genpath('stimuli'))
% CONTEXT:
% 0 = NEITHER
% 1 = PARANOID
% 2 = CHEATING
% load in audio data and specify where the project is located
% laptop = /Volumes/norman/amennen/github/greenEyes/
if fmri == 1 % this is just if you're in the scanner room or not but it will always look for triggers
    repo_path ='/Data1/code/rt-cloud/projects/greenEyes/';
else
    repo_path = '/Volumes/norman/amennen/github/brainiak/rt-cloud/projects/greenEyes/';
end
display_path = [repo_path 'display'];

cd(display_path);
wavfilename = [display_path '/stimuli/greenMyeyes_Edited.wav'];
data_path = fullfile(display_path,['data/' bidsId]);
runHeader = fullfile(data_path, runId);
if ~exist(runHeader)
    mkdir(runHeader)
end

classOutputDir = [repo_path 'data' '/' bidsId '/'  'ses-02' '/'];
%classOutputDir = [runHeader '/classoutput'];
if ~exist(classOutputDir)
    mkdir(classOutputDir)
end
%%
%initialize system time calls
seed = sum(100*clock); %get random seed
GetSecs;

% open and set-up output file
dataFile = fopen([runHeader '/behavior.txt'],'a');
fprintf(dataFile,'\n*********************************************\n');
fprintf(dataFile,'* GreenEyes v.1.0\n');
fprintf(dataFile,['* Date/Time: ' datestr(now,0) '\n']);
fprintf(dataFile,['* Seed: ' num2str(seed) '\n']);
fprintf(dataFile,['* Subject Number: ' num2str(runData.subjectNum) '\n']);
fprintf(dataFile,['* Subject Name: ' runData.subjectName '\n']);
fprintf(dataFile,['* Run Number: ' num2str(runData.run) '\n']);
fprintf(dataFile,['* Use Button Box: ' num2str(useButtonBox) '\n']);
fprintf(dataFile,['* rtData: ' num2str(rtData) '\n']);
fprintf(dataFile,['* debug: ' num2str(debug) '\n']);
fprintf(dataFile,'*********************************************\n\n');

% print header to command window
fprintf('\n*********************************************\n');
fprintf('* GreenEyes v.1.0\n');
fprintf(['* Date/Time: ' datestr(now,0) '\n']);
fprintf(['* Seed: ' num2str(seed) '\n']);
fprintf(['* Subject Number: ' num2str(runData.subjectNum) '\n']);
fprintf(['* Subject Name: ' runData.subjectName '\n']);
fprintf(['* Run Number: ' num2str(runData.run) '\n']);
fprintf(['* Use Button Box: ' num2str(useButtonBox) '\n']);
fprintf(['* rtData: ' num2str(rtData) '\n']);
fprintf(['* debug: ' num2str(debug) '\n']);
fprintf('*********************************************\n\n');

%% Initalizing scanner parameters

disdaqs = 15; % how many seconds to drop at the beginning of the run
TR = 1.5; % seconds per volume
% story duration is 11 minutes 52 seconds
% sotry ends at 11 minutes 36.5 seconds
audioDur = 712; % seconds how long the entire autioclip is
runDur = audioDur;
nTRs_run = ceil(runDur/TR);

% so we want 485 TRs total with the beginning 10 TRs
if (~debug) %so that when debugging you can do other things
    Screen('Preference', 'SkipSyncTests', 2);
    ListenChar(2);  %prevent command window output
    HideCursor;     %hide mouse cursor
    
else
    Screen('Preference', 'SkipSyncTests', 2);
end

% display parameters
textColor = 0;
textFont = 'Arial';
textSize = 30;
textSpacing = 25;
fixColor = 0;
backColor = 127;
fixationSize = 4;% pixels
minimumDisplay = 0.25;
KbName('UnifyKeyNames');
LEFT = KbName('1!');
subj_keycode = LEFT;
RIGHT = KbName('2@');
%TRIGGER = '5%'; % for Penn/rtAttention experiment at Princeton
TRIGGER ='=+'; %put in for Princeton scanner -- default setup
TRIGGER_keycode = KbName(TRIGGER);
probe_keys = [LEFT RIGHT];
key_map = zeros(1,256);
key_map(LEFT) = 1;
key_map(RIGHT) = 1;
key_map(TRIGGER_keycode) = 1;

if mod(runData.subjectNum,2) == 0
    runData.LEFT_PRESS = 'CHEATING';
    runData.RIGHT_PRESS = 'PARANOID';
elseif mod(runData.subjectNum,2) == 1
    runData.LEFT_PRESS = 'PARANOID';
    runData.RIGHT_PRESS = 'CHEATING';
end

% set default device to be -1
DEVICE = -1;
if useButtonBox && (~debug)
    DEVICENAME = 'Current Designs, Inc. 932';
    [index devName] = GetKeyboardIndices;
    for device = 1:length(index)
        if strcmp(devName(device),DEVICENAME)
            DEVICE = index(device);
        end
    end
elseif ~useButtonBox && fmri
    % let's set it to look for the Dell keyboard instead
    DEVICENAME = 'Dell KB216 Wired Keyboard';
    [index devName] = GetKeyboardIndices;
    for device = 1:length(index)
        if strcmp(devName(device),DEVICENAME)
            DEVICE = index(device);
        end
    end
end



% CIRCLE PARAMETERS + FONT SIZE GOES HERE
circleRadius=100;
restCircleColor=[196 193 192];
recordingCircleColor=[179 30 25];
maxGreenCircleColor=[90 204 2];
badColor = 50*[1 1 1];

% RECTANGLE PARAMETERS GO HERE
rectWidth = 100;
rectHeight = 300;

circleFontSize = 60;
feedbackDur = 2; % seconds - how long to show feedback
deltat = .1;
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
    screenX = 1200;
    screenY = 1200;
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
    % for PRINCETON
    screenX = 1280;
    screenY = 720;
    %     %to ensure that the images are standardized (they take up the same degrees of the visual field) for all subjects
    %     if (screenX ~= ScreenResX) || (screenY ~= ScreenResY)
    %         fprintf('The screen dimensions may be incorrect. For screenNum = %d,screenX = %d (not 1152) and screenY = %d (not 864)',screenNum, screenX, screenY);
    %     end
end

%create main window
mainWindow = Screen(screenNum,'OpenWindow',backColor,[0 0 screenX screenY]);
ifi = Screen('GetFlipInterval', mainWindow);
slack  = ifi/2;
% details of main window
centerX = screenX/2; centerY = screenY/2;
Screen(mainWindow,'TextFont',textFont);
Screen(mainWindow,'TextSize',textSize);
fixDotRect = [centerX-fixationSize,centerY-fixationSize,centerX+fixationSize,centerY+fixationSize];
circleDotRect = [centerX-circleRadius,centerY-circleRadius,centerX+circleRadius,centerY+circleRadius];
rect = [centerX-rectWidth/2,centerY-rectHeight/2,centerX+rectWidth/2,centerY+rectHeight/2];
lineW=100;
penW=10;
Priority(MaxPriority(screenNum));

%% check audio volume in the scanner
if fmri
    %AUDIO_DEVICENAME = 'HDA Creative: ALC898 Analog (hw:3,0)';
    AUDIO_DEVICENAME = 'HDA Creative: ALC898 Analog';
    AUDIO_devices=PsychPortAudio('GetDevices');
    for dev = 1:length(AUDIO_devices)
        devName = AUDIO_devices(dev).DeviceName;
        %if strcmp(devName,AUDIO_DEVICENAME)
        if length(devName) > length(AUDIO_DEVICENAME)
            if all(AUDIO_DEVICENAME==devName(1:length(AUDIO_DEVICENAME)))
                AUDIODEVICE = AUDIO_devices(dev).DeviceIndex;
            end
        end
    end
end

%% Load in audio data for story
%

[y, freq] = audioread(wavfilename);
wavedata = y';
nrchannels = size(wavedata,1); % Number of rows
if ~debug
    ListenChar(2);
end

if ~fmri
    pahandle = PsychPortAudio('Open', [], [], [], freq, nrchannels);
else
    pahandle = PsychPortAudio('Open', AUDIODEVICE, [], [], freq, nrchannels);
end
PsychPortAudio('FillBuffer', pahandle, wavedata);

%% LOAD IN THE STATION TRS %%
musicDur = 18; % how long the music lasts
silenceDur1 = 3;
storyTRs = 25:475;
nTRs_story = length(storyTRs);
nTRs_music = musicDur/TR;
stationTRs = zeros(nTRs_story,1); % actual files wer're going to use to test classifier
recordedTRs = zeros(nTRs_story,1);
st = load('stationsMat.mat');
nStations = 7; %size(st.stationsDict,2);
for s = 1:nStations
    this_station_TRs = st.stationsDict{s} + 1;
    stationTRs(this_station_TRs) = s;
    recordedTRs(this_station_TRs-3) = s;
end
% now make array specifying which station to look for
lookTRs = zeros(nTRs_story,1);
for t = 1:nTRs_story
    pastStation = max(stationTRs(1:t));
    lastTRForStation = find(stationTRs == pastStation);
    lastTRForStation = lastTRForStation(end);
    if pastStation > 0 && (t-lastTRForStation <=10)
        lookTRs(t) = pastStation;
    end
end
% make all look TRs during recording parts 0
lookTRs(recordedTRs>0) = 0;
lookTRs(stationTRs>0) = 0;
runData.stationScore = NaN(nStations,1);
runData.stationFeedbackGiven = {};
%% show them instructions until they press to begin
continueInstruct = '\n\n-- Please press your INDEX to continue once you understand these instructions. --';
startInstruct = '\n\n-- Please press your INDEX to start the task once you are ready to begin your mission. --';

% show instructions
Screen(mainWindow,'FillRect',backColor);
Screen('Flip',mainWindow);
FlushEvents('keyDown');

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% before anything else just brief them on listening to the story, either
% for the first time or again
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

firstRun = ['Welcome to the task!\n\nToday you will be listening to a pre-recorded audio story. \nAs explained earlier, please do you best to complete the mission and discover the truth.'];
if runData.run == 1
    % show the first instructions
    firstInstruct = [firstRun continueInstruct];
    DrawFormattedText(mainWindow,firstInstruct,'center','center',textColor,70,[],[],1.2);
    Screen('Flip',mainWindow);
    waitForKeyboard(subj_keycode,DEVICE);
end
firstRun = ['Remember, you need to investigate who else is in Lee''s bed:\n(1)if Arthur''s wife, Joanie, is cheating on him with Lee, then Joanie is in Lee''s bed.\n\n(2) if Arthur is paranoid, then Lee''s girlfriend, Rose in in Lee''s bed.\n One of these options is correct, and the other is incorrect.'];
%if runData.run == 1
% show the first instructions
firstInstruct = [firstRun continueInstruct];
DrawFormattedText(mainWindow,firstInstruct,'center','center',textColor,70,[],[],1.2);
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);
%end

reminder = ['Each time you listen to the story, you should always pay attention to the neurofeedback\nand use it to bias your interpretation of your story.\nEven if you think that the story has directly revealed which interpretation is correct, characters might be lying.\nYour job is to try to interpret the story according to what the neurofeedback is telling you,\nnot to try to figure out which interpretation the author intended.'];
reminderInstruct = [reminder continueInstruct];
DrawFormattedText(mainWindow,reminderInstruct,'center','center',textColor,70,[],[],1.2);
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);

% now tell them they will listen again and ge
nextInstruct = ['Please stay focused, keep listening throughout the entire story, and use your neurofeedback clues to help you along the way.' continueInstruct];
DrawFormattedText(mainWindow,nextInstruct,'center','center',textColor,70,[],[],1.2);
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);


nextInstruct = ['Remember to take breaks before starting the task so you can succeed on your mission!' startInstruct];
DrawFormattedText(mainWindow,nextInstruct,'center','center',textColor,70,[],[],1.2);
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);

%waitForKeyboard(subj_keycode,DEVICE);
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
%% Wait for first trigger in the scanner
if (~debug )
    timing.trig.wait = WaitTRPulse(TRIGGER_keycode,DEVICE);
    runStart = timing.trig.wait;
    DrawFormattedText(mainWindow,STILLREMINDER,'center','center',textColor,70);
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
Screen(mainWindow,'TextSize',circleFontSize); % starts at 30
DrawFormattedText(mainWindow,'+','center','center',textColor,70);
Screen('Flip', mainWindow);
Screen(mainWindow,'TextSize',textSize);
%%

% calculate onset of story
audioOnset = disdaqs;
volStart = 1 + disdaqs/TR ; % this should be on the 11th trigger
timing.plannedOnsets.audioStart = audioOnset + runStart;

% actual playing
% wait for first trigger
Screen('FillRect', mainWindow,restCircleColor, rect);
[timing.trig.pulses(volStart) runData.pulses(volStart)] = WaitTRPulse(TRIGGER_keycode,DEVICE,timing.plannedOnsets.audioStart);
Screen('Flip', mainWindow); % show the rectangle once the story starts

timing.actualOnsets.audioStart = PsychPortAudio('Start', pahandle, [], timing.plannedOnsets.audioStart,1);
fprintf('delay is %8.8f\n', timing.plannedOnsets.audioStart-timing.actualOnsets.audioStart)

%% Now record all the triggers from the scanner
% calculate onsets for all subsequent TRs in the scanner
% goal: record every trigger during the story
% music starts at 15

% *** NOW *** ADDING STATIONS FROM STATION MATRIX
runData.classOutputFileLoad = zeros(nTRs_story,nStations);
runData.leftPress = NaN(1,nTRs_story);
runData.leftPressRT = NaN(1,nTRs_story);
runData.rightPress = NaN(1,nTRs_story);
runData.rightPressRT = NaN(1,nTRs_story);
timing.probeResp = zeros(1,nStations);
timing.plannedOnsets.story = timing.plannedOnsets.audioStart + musicDur + silenceDur1 + [0 cumsum(repmat(TR, 1,nTRs_story-1))];
% get all timing for stations starrt
% then subtract that by 4
timing.plannedOnsets.station = zeros(nStations,1);
for st = 1:nStations
    this_station_TRs = find(recordedTRs == st);
    first_TR = this_station_TRs(1);
    timing.plannedOnsets.stationREC(st) = timing.plannedOnsets.story(first_TR);
    timing.plannedOnsets.probeON(st) = timing.plannedOnsets.stationREC(st) - 4; % show it 4 s before station start
    timing.plannedOnsets.probeOFF(st) = timing.plannedOnsets.stationREC(st) - 2;
end
timing.actualOnsets.story = NaN(nTRs_story,1);
runData.pulses = NaN(nTRs_run,1);
% prepare for trial sequence
% want displayed: run, volume TR, story TR, tonsset dif, pulse,
fprintf(dataFile,'%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s\n', 'run', 'TR', 'storyTR', 'tondiff', 'trig','LEFT', 'RIGHT', 'station', 'looking', 'loaded', 'p(cor)')
fprintf('%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s\n', 'run', 'TR', 'storyTR', 'tondiff', 'trig', 'LEFT', 'RIGHT', 'station', 'looking', 'loaded', 'p(cor)')
%%
KbQueueCreate(DEVICE,key_map);
KbQueueStart;
KbQueueFlush(DEVICE);
SHOWINGFEEDBACK = 0;
Screen(mainWindow,'TextFont',textFont);
Screen(mainWindow,'TextSize',circleFontSize); % starts at 30
lastStation = 1; % initalize for indexing
probe_start = zeros(nStations,1); % did we start the probe yet for that station
probe_stop = zeros(nStations,1);
timing.actualOnsets.probeON = NaN(nStations,1);
timing.actualOnsets.probeOFF = NaN(nStations,1);
keep_display = 0;
for iTR = 1:nTRs_story
    volCounter = storyTRs(iTR); % what file number this story TR actually is
    isStation = stationTRs(iTR);
    isRecording = recordedTRs(iTR);
    isLookingStation = lookTRs(iTR);
    next_TRs = stationTRs(find(stationTRs(iTR:end)) + iTR - 1);
    if ~isempty(next_TRs)
        nextStation = next_TRs(1); % if at end, don't update next_station
    end
%     if ~isStation && stationTRs(iTR + 3)
%         % now display start probe
%         
%     end
%     
%     if ~isStation && stationTRs(iTR + 2)
%        % remove display 
%         
%     end
%     if isRecording && ~stationTRs(iTR-1)
%         % check for press now
%         thisStation = isRecording;
%         [~, key_code] = KbQueueCheck(DEVICE);
%         if any(key_code)
%             pressed_keys = find(key_code);
%             [sorted_key_code, sort_ind] = sort(key_code(pressed_keys));%sorts it so you look for the first valid choice
%             pressed_keys = pressed_keys(sort_ind);
%             if any(ismember(pressed_keys,probe_keys))
%                 isvalid_press = true;
%             else
%                 isvalid_press = false;
%             end
%             if isvalid_press % pressed at least one correct key
%                 % prepare response data for first keypress only
%                 timing.probeResp(thisStation) = min(key_code(key_code>0));
%                 runData.probeResp(thisStation) = KbName(find(key_code == keyTime,1));
%             end
%         else
%             pressed_keys = [];
%         end
% 
%         KbQueueRelease(DEVICE);
%     end
    if SHOWINGFEEDBACK
        if (GetSecs - timing.startFeedbackDisplay(lastStation)) >= 0.5 %(feedbackDur-slack)
            Screen(mainWindow, 'FillRect', restCircleColor, rect)
            timespec = timing.startFeedbackDisplay(lastStation) + feedbackDur - slack;
            timing.stopFeedbackDisplay(lastStation) = Screen('Flip', mainWindow,timespec);
            Screen('FillRect', mainWindow,restCircleColor, rect);
            SHOWINGFEEDBACK = 0;
        else % redraw so can flip on next TR anyway
            Screen('DrawLine',mainWindow, 0,rect(1)-lineW,centerY,rect(3)+lineW,centerY,[7])
            Screen(mainWindow, 'FillRect', restCircleColor, rect)
            feedbackRect = rect;
            feedbackRect(2) = rect(4) - (rect(4) - rect(2))*this_ev;
            if this_ev <= 0.5
                Screen(mainWindow,'FillRect', badColor, feedbackRect);
                bonus_points = sprintf('$%2.2f', 0);
            else
                Screen(mainWindow,'FillRect', maxGreenCircleColor, feedbackRect);
                bonus_points = sprintf('$%2.2f', this_ev);
            end
            runData.stationFeedbackGiven{lastStation} = bonus_points; % what people will see
            tempBounds = Screen('TextBounds', mainWindow, bonus_points);
            Screen('drawtext',mainWindow,bonus_points,centerX-tempBounds(3)/2,feedbackRect(4)+(centerY/10)-tempBounds(4)/2,[0 0 0]);
        end
    elseif isRecording > 0
        Screen('FillRect', mainWindow,recordingCircleColor, rect)
        
    else % not showing feedback and not recording--most likely probe will be here
        Screen('FillRect', mainWindow,restCircleColor, rect);

        %fprintf('here\n')
        if keep_display
            Screen('drawtext',mainWindow,'INDEX',centerX - centerX/2 -tempBounds_IND(3)/2,centerY-rectHeight/2 - tempBounds_IND(4)/2,textColor);
            Screen('drawtext',mainWindow,runData.LEFT_PRESS,centerX - centerX/2 -tempBounds_L(3)/2,centerY - tempBounds_L(4)/2,textColor);
            Screen('drawtext',mainWindow,'MIDDLE',centerX+centerX/2+tempBounds_MID(3)/2,centerY-rectHeight/2 - tempBounds_MID(4)/2,textColor);
            Screen('drawtext',mainWindow,runData.RIGHT_PRESS,centerX+centerX/2+tempBounds_R(3)/2,centerY - tempBounds_R(4)/2,textColor);
        end
        if ~probe_start(nextStation) && abs(GetSecs - timing.plannedOnsets.probeON(nextStation)) <= 1
            %fprintf('HERE IN ON')
            %KbQueueCreate(DEVICE,key_map);
            %KbQueueStart(DEVICE);
            probe_start(nextStation) = 1;
            % put display on and look for keypress
            % will likely need to keep putting this up
            keep_display = 1;
            tempBounds_IND = Screen('TextBounds', mainWindow, 'INDEX');
            tempBounds_MID = Screen('TextBounds', mainWindow, 'MIDDLE');
            tempBounds_L = Screen('TextBounds', mainWindow, runData.LEFT_PRESS);
            tempBounds_R = Screen('TextBounds', mainWindow, runData.RIGHT_PRESS);
            Screen('drawtext',mainWindow,'INDEX',centerX - centerX/2 -tempBounds_IND(3)/2,centerY-rectHeight/2 - tempBounds_IND(4)/2,textColor);
            Screen('drawtext',mainWindow,runData.LEFT_PRESS,centerX - centerX/2 -tempBounds_L(3)/2,centerY - tempBounds_L(4)/2,textColor);
            Screen('drawtext',mainWindow,'MIDDLE',centerX+centerX/2+tempBounds_MID(3)/2,centerY-rectHeight/2 - tempBounds_MID(4)/2,textColor);
            Screen('drawtext',mainWindow,runData.RIGHT_PRESS,centerX+centerX/2+tempBounds_R(3)/2,centerY - tempBounds_R(4)/2,textColor);
            %KbQueueFlush(DEVICE);
            timespec = timing.plannedOnsets.probeON(nextStation) - slack;
            timing.actualOnsets.probeON(nextStation) = Screen('Flip',mainWindow,timespec); % flip as soon as it's ready
            Screen('FillRect', mainWindow,restCircleColor, rect);
            Screen('drawtext',mainWindow,'INDEX',centerX - centerX/2 -tempBounds_IND(3)/2,centerY-rectHeight/2 - tempBounds_IND(4)/2,textColor);
            Screen('drawtext',mainWindow,runData.LEFT_PRESS,centerX - centerX/2 -tempBounds_L(3)/2,centerY - tempBounds_L(4)/2,textColor);
            Screen('drawtext',mainWindow,'MIDDLE',centerX+centerX/2+tempBounds_MID(3)/2,centerY-rectHeight/2 - tempBounds_MID(4)/2,textColor);
            Screen('drawtext',mainWindow,runData.RIGHT_PRESS,centerX+centerX/2+tempBounds_R(3)/2,centerY - tempBounds_R(4)/2,textColor);
        elseif ~probe_stop(nextStation) && (GetSecs - timing.actualOnsets.probeON(nextStation)) >= 0.5
            % just go back to a regular display
            %fprintf('here in OFF')
            keep_display = 0;
            timespec = timing.plannedOnsets.probeOFF(nextStation) - slack;
            timing.actualOnsets.probeOFF(nextStation) = Screen('Flip',mainWindow,timespec);
            probe_stop(nextStation) = 1;
            Screen('FillRect', mainWindow,restCircleColor, rect);
        end
        
    end
    
%     [keyIsDown, keyCode] = KbQueueCheck(DEVICE);
%     if keyCode(LEFT) || keyCode(RIGHT)
%         if keyCode(LEFT)
%             runData.leftPressRT(iTR) = keyCode(LEFT);
%         end
%         if keyCode(RIGHT)
%             runData.rightPressRT(iTR) = keyCode(RIGHT);
%         end
%     end
    timespec = timing.plannedOnsets.story(iTR) - slack;
    %a(iTR) = GetSecs;
    [timing.trig.pulses(volCounter) runData.pulses(volCounter) runData.leftPressRT(iTR), runData.rightPressRT(iTR)] = WaitTRPulse_KbQueue(TRIGGER_keycode,DEVICE,timing.plannedOnsets.story(iTR));
    %b(iTR) = GetSecs;
    %b(iTR)-a(iTR)
    timing.actualOnsets.story(iTR) = Screen('Flip',mainWindow,timespec);
    KbQueueFlush(DEVICE);
    %c(iTR) = GetSecs;
    if runData.leftPressRT(iTR) > 0
        runData.leftPress(iTR) = 1;
    end
    if runData.rightPressRT(iTR) > 0
        runData.rightPress(iTR) = 1;
    end
    % check if there's any updated score available
    if isLookingStation > 0 % skip this if you just started story
        % if you haven't given feedback yet for that station and you're within
        % 10 TRs (something went wrong/skip otherwise)
        lastStation = isLookingStation;
        if rtData
            if isnan(runData.stationScore(lastStation))
                % look for output
                timing.classifierLoadStart(iTR,lastStation) = GetSecs;
                tClassOutputFileTimeout = GetSecs + deltat;
                while (~runData.classOutputFileLoad(iTR,lastStation) && (GetSecs < tClassOutputFileTimeout))
                    [runData.classOutputFileLoad(iTR,lastStation) runData.classOutputFile{iTR,lastStation}] = GetSpecificClassOutputFile(classOutputDir,runData.run,lastStation-1,usepython); %#ok<AGROW>
                end
                % now if file exists load score
                if runData.classOutputFileLoad(iTR,lastStation)
                    timing.classifierStationFound(iTR,lastStation) = GetSecs;
                    tempStruct = load([classOutputDir '/' runData.classOutputFile{iTR,lastStation}]);
                    if ~usepython
                        runData.stationScore(lastStation) = tempStruct.classOutput;
                    else
                        runData.stationScore(lastStation) = tempStruct;
                    end
                    this_ev = runData.stationScore(lastStation);
                    Screen('DrawLine',mainWindow, 0,rect(1)-lineW,centerY,rect(3)+lineW,centerY,[7])
                    Screen(mainWindow, 'FillRect', restCircleColor, rect)
                    feedbackRect = rect;
                    feedbackRect(2) = rect(4) - (rect(4) - rect(2))*this_ev;
                    if this_ev <= 0.5
                        Screen(mainWindow,'FillRect', badColor, feedbackRect);
                        bonus_points = sprintf('$%2.2f', 0);
                    else
                        Screen(mainWindow,'FillRect', maxGreenCircleColor, feedbackRect);
                        bonus_points = sprintf('$%2.2f', this_ev);
                    end
                    runData.stationFeedbackGiven{lastStation} = bonus_points; % what people will see
                    tempBounds = Screen('TextBounds', mainWindow, bonus_points);
                    Screen('drawtext',mainWindow,bonus_points,centerX-tempBounds(3)/2,feedbackRect(4)+(centerY/10)-tempBounds(4)/2,[0 0 0]);
                    timing.startFeedbackDisplay(lastStation) = Screen('Flip',mainWindow); % flip as soon as it's ready
                    SHOWINGFEEDBACK = 1; % ARE WE CURRENTLY DISPLAYING FEEDBACK
                else
                    runData.classOutputFile{iTR,lastStation} = 'not ready';
                end
                
            end
        end
    else
        %  lastStation = 1; % initialize it here for print
    end
    % print out TR information
    fprintf(dataFile,'%-8d%-8d%-8d%-8.3f%-8d%-8df%-8df%-8d%-8d%-8d%-8.3f\n', runNum,volCounter,iTR,timing.actualOnsets.story(iTR)-timing.plannedOnsets.story(iTR),runData.pulses(volCounter),runData.leftPress(iTR),runData.rightPress(iTR),isStation,isLookingStation,runData.classOutputFileLoad(iTR,lastStation),runData.stationScore(lastStation));
    fprintf('%-8d%-8d%-8d%-8.3f%-8d%-8d%-8df%-8d%-8d%-8d%-8.3f\n', runNum,volCounter,iTR,timing.actualOnsets.story(iTR)-timing.plannedOnsets.story(iTR),runData.pulses(volCounter),runData.leftPress(iTR),runData.rightPress(iTR),isStation,isLookingStation,runData.classOutputFileLoad(iTR,lastStation),runData.stationScore(lastStation));
end

Screen(mainWindow,'TextSize',textSize);
Screen(mainWindow,'TextFont',textFont);

%%
% Stop playback:
[timing.PPAstop.startTime timing.PPAstop.endPos timing.PPAstop.xruns timing.PPAstop.estStopTime] = PsychPortAudio('Stop', pahandle,1);
% IF WANT TO STOP IMMEDIATELY
%    [startTime endPos xruns estStopTime] = PsychPortAudio('Stop', pahandle,0);
% Close the audio device:
PsychPortAudio('Close', pahandle);
% WaitSecs(10);

%% DISPLAY THEIR TOTAL SCORE HERE
all_rewards = runData.stationScore;
all_rewards(all_rewards<=0.5) = 0;
runData.reward = nanmean(all_rewards)*5;
rewardMessage = sprintf('Run %i earnings: $%2.2f',runNum, runData.reward);
tempBounds = Screen('TextBounds', mainWindow, rewardMessage);
Screen('drawtext',mainWindow,rewardMessage,centerX-tempBounds(3)/2,centerY-tempBounds(4)/2,textColor);
Screen('Flip', mainWindow);
WaitSecs(5);
%% save everything
file_name = ['behavior_run' num2str(runData.run) '_' datestr(now,30) '.mat'];
save(fullfile(runHeader,file_name),'timing', 'runData');

%% ADD MESSAGE THAT SAYS THEIR TOTAL SCORE HERE!!

sca;
ShowCursor;
ListenChar;
end
