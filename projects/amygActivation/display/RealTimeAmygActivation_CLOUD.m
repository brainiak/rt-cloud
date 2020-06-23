% Display for Green Eyes sample experiment where we just want the subject
% to listen to the story!
% load necessary scanner settings

% wait 5 TR's before starting story?
% TO DO: % RANDOMIZE WHICH  SIZE CHEATING/PARANOID SIDE IS FOR EACH PERSON!
function RealTimeAmygActivation_CLOUD(toml_file, runNum)

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
bidsId = sprintf('sub-%03d',runData.subjectNum);
sesId = sprintf('ses-%02d', cfg.subjectDay);
runId = sprintf('run-%02d',runData.run);

debug = cfg.display.debug;
useButtonBox = cfg.display.useButtonBox;
rtData = cfg.display.rtData; % if this is 0, then have a practice/transfer run but no neurofeedback

repo_path = [cfg.local.rtcloudDir '/projects/amygActivation/'];
fmri_path = [repo_path 'data' '/' bidsId '/' sesId];
display_path = [repo_path 'display'];
cd(display_path);
data_path = fullfile(display_path,['data/' bidsId]);
% run directory controlling the display and display data
runDir_display = fullfile(data_path, sesId,runId);
if ~exist(runDir_display)
    mkdir(runDir_display)
end
% this is the run dir from the processing pipeline
runDir_rtcloud = [repo_path 'data' '/' bidsId '/'  sesId '/' runId '/'];
if ~exist(runDir_rtcloud)
    mkdir(runDir_rtcloud)
end
%%
%initialize system time calls
seed = sum(100*clock); %get random seed
GetSecs;

% open and set-up output file
dataFile = fopen([runDir_display '/behaviorLog.txt'],'a');
fprintf(dataFile,'\n*********************************************\n');
fprintf(dataFile,'* AmygActivation v.1.0\n');
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
fprintf('* AmygActivation v.1.0\n');
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

TR = 1.5; % seconds per volume
disdaqs = cfg.nTR_skip*TR; % how many seconds to drop at the beginning of the run
nTRs_run = cfg.nTR_run;

% so we want 379 TRs total with the beginning 10 TRs
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
%TRIGGER = '5%'; % for Penn
TRIGGER ='=+'; %put in for Princeton scanner -- default setup
TRIGGER_keycode = KbName(TRIGGER);
probe_keys = [LEFT RIGHT];
key_map = zeros(1,256);
key_map(LEFT) = 1;
key_map(RIGHT) = 1;
key_map(TRIGGER_keycode) = 1;

if mod(runData.subjectNum,2) == 0
    runData.LEFT_PRESS = 'ODD';
    runData.RIGHT_PRESS = 'EVEN';
elseif mod(runData.subjectNum,2) == 1
    runData.LEFT_PRESS = 'EVEN';
    runData.RIGHT_PRESS = 'ODD';
end

% set default device to be -1
DEVICE = -1;
%%% update the code here to add the button box device,
%%% or custom keyboard. setting a specific number will
%%% help the code look for new triggers faster.
%%% to see all possible USB keyboards, run
%%% [index devName] = GetKeyboardIndices
%%% and look at all the devNames
% BUTTON_BOX_DEVICENAME = [];
% if useButtonBox && (~debug)
%     DEVICENAME = 'Current Designs, Inc. 932';
%     [index devName] = GetKeyboardIndices;
%     for device = 1:length(index)
%         if strcmp(devName(device),DEVICENAME)
%             DEVICE = index(device);
%         end
%     end
% elseif ~useButtonBox && fmri
%     % let's set it to look for the Dell keyboard instead
%     DEVICENAME = 'Dell KB216 Wired Keyboard';
%     [index devName] = GetKeyboardIndices;
%     for device = 1:length(index)
%         if strcmp(devName(device),DEVICENAME)
%             DEVICE = index(device);
%         end
%     end
% end

% RECTANGLE PARAMETERS GO HERE
rectWidth = 100;
rectHeight = 300;
restColor=[196 193 192];
maxGreenColor=[90 204 2];
badColor = 50*[1 1 1];
rectFontSize = 60;
deltat = .1;
wrapChars=50;
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
    
    % if you're using 2 monitors, and you just want half of the screen
    % width to be used, use this command:
    %resolution = Screen('Resolution', screenNum);
    %windowSize.pixels = [resolution.width/2 resolution.height];
    %screenX = windowSize.pixels(1);
    %screenY = windowSize.pixels(2);
    % OR, set it manually if you know the resolution of the projector
    % for PRINCETON
    %screenX = 1280;
    %creenY = 720;
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
rect = [centerX-rectWidth/2,centerY-rectHeight/2,centerX+rectWidth/2,centerY+rectHeight/2];
lineW=100;
penW=10;
Priority(MaxPriority(screenNum));



%% LOAD IN THE REGRESSOR MATRIX%%

regressor_filename = [runDir_rtcloud '/' 'regressor_' runId '.mat']; % THESE ARE NOT SHIFTED FOR THE HRF!!!
regressor_struct = load(regressor_filename);
regressor = regressor_struct.regressor;
nTRs_task = length(regressor);
happyTRs_display = find(regressor == cfg.HAPPY); % actual files wer're going to use to test classifier
happyTRs_shifted = happyTRs_display + cfg.nTR_shift;
mathTRs_display = find(regressor == cfg.MATH);
% make a vector with all TRs where you'll be looking for a file
recordedTRs = zeros(nTRs_task,1);
recordedTRs(happyTRs_shifted) = 1; % we're only giving feedback during happy TRs
runData.feedbackScore = NaN(nTRs_task,1);
runData.feedbackScoreSmoothed = NaN(nTRs_task,1);
runData.feedbackGiven = {};
runData.rtData = rtData;
%% show them instructions until they press to begin
continueInstruct = '\n\n-- Please press your INDEX to continue once you understand these instructions. --';
startInstruct = '\n\n-- Please press your INDEX to start the task once you are ready to begin. --';

% show instructions
Screen(mainWindow,'FillRect',backColor);
Screen('Flip',mainWindow);
FlushEvents('keyDown');

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% before anything else just brief them on listening to the story, either
% for the first time or again
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

firstRun = ['Welcome to the task!\n\nToday you will be trying to maximize the bar to increase your reward earnings.'];
if runData.run == 1
    % show the first instructions
    firstInstruct = [firstRun continueInstruct];
    DrawFormattedText(mainWindow,firstInstruct,'center','center',textColor,wrapChars,[],[],1.2);
    Screen('Flip',mainWindow);
    waitForKeyboard(subj_keycode,DEVICE);
end

reminder = ['Remember, when you see "HAPPY", think of happy memories to increase the bar height and, thus, increase reward.'];
reminderInstruct = [reminder continueInstruct];
DrawFormattedText(mainWindow,reminderInstruct,'center','center',textColor,wrapChars,[],[],1.2);
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);

nextInstruct = ['Please stay focused, and use your neurofeedback to keep trying to maximize the signal.' continueInstruct];
DrawFormattedText(mainWindow,nextInstruct,'center','center',textColor,wrapChars,[],[],1.2);
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);

% now tell them about the math blocks
nextInstruct = ['When you see "MATH" and a number inside the bar,\npress your INDEX or MIDDLE finger\nfor an even or odd number.' continueInstruct];
DrawFormattedText(mainWindow,nextInstruct,'center','center',textColor,wrapChars,[],[],1.2);
Screen('Flip',mainWindow);
waitForKeyboard(subj_keycode,DEVICE);


nextInstruct = ['Remember to take breaks before starting the task so you can succeed on your mission!' startInstruct];
DrawFormattedText(mainWindow,nextInstruct,'center','center',textColor,wrapChars,[],[],1.2);
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
%% Wait for first trigger in the scanner
if (~debug )
    timing.trig.wait = WaitTRPulse(TRIGGER_keycode,DEVICE);
    runStart = timing.trig.wait;
    DrawFormattedText(mainWindow,STILLREMINDER,'center','center',textColor,wrapChars);
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
Screen(mainWindow,'TextSize',rectFontSize); % starts at 30
DrawFormattedText(mainWindow,'+','center','center',textColor,wrapChars);
Screen('Flip', mainWindow);
Screen(mainWindow,'TextSize',textSize);
%%

% calculate onset of story
volStart = 1 + disdaqs/TR ; % this should be on the 11th trigger
taskTRs = volStart:(volStart + nTRs_task - 1); 
%% Now record all the triggers from the scanner
% calculate onsets for all subsequent TRs in the scanner
% goal: record every trigger during the story

runData.OutputFileLoad = zeros(nTRs_task);
runData.leftPress = NaN(1,nTRs_task);
runData.leftPressRT = NaN(1,nTRs_task);
runData.rightPress = NaN(1,nTRs_task);
runData.rightPressRT = NaN(1,nTRs_task);

timing.plannedOnsets.TR = runStart + disdaqs + [0 cumsum(repmat(TR, 1,nTRs_task-1))];
% get all timing for stations starrt
% then subtract that by 4
timing.actualOnsets.TR = NaN(1,nTRs_task);
timing.leftPressRT = NaN(nTRs_run,1);
timing.rightPressRT = NaN(nTRs_run,1);
runData.pulses = NaN(nTRs_run,1);
runData.pulses = NaN(nTRs_run,1);

% prepare for trial sequence
% want displayed: run, volume TR, story TR, tonsset dif, pulse,
fprintf(dataFile,'%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s\n', 'run','block', 'volume', 'iTR', 'tondiff', 'trig','LEFT', 'RIGHT', 'loaded', 'score');
fprintf('%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s%-8s\n', 'run', 'block','volume', 'iTR', 'tondiff', 'trig', 'LEFT', 'RIGHT',  'loaded', 'score');
%%
KbQueueCreate(DEVICE,key_map);
KbQueueStart;
KbQueueFlush(DEVICE);
SHOWINGFEEDBACK = 0;
Screen(mainWindow,'TextFont',textFont);
Screen(mainWindow,'TextSize',rectFontSize); % starts at 30
%%%%%%%%%%%%%%%%% get temp bounds for block types centering
tempBounds_L = Screen('TextBounds', mainWindow, runData.LEFT_PRESS);
tempBounds_R = Screen('TextBounds', mainWindow, runData.RIGHT_PRESS);
tempBounds_REST = Screen('TextBounds', mainWindow, 'REST');
tempBounds_MATH = Screen('TextBounds', mainWindow, 'MATH');
tempBounds_HAPPY = Screen('TextBounds', mainWindow, 'HAPPY');
%%%%%%%%%%%%%%%%% get temp bounds for block types centering

keep_display = 0;
initialScore = 0.5;
blockTypeStr = 'None';
for iTR = 1:nTRs_task
    leftPress = 0;
    rightPress = 0;
    volCounter = taskTRs(iTR); % what file number this story TR actually is
    blockType = regressor(iTR); % this will say if it's resting, happy, or math    
    % set the display for each of the block types BEFORE flipping
    if blockType == cfg.REST
       blockTypeStr = 'REST';
       % here just show the grey bar so don't need to change anything
       % add text that says rest
       Screen(mainWindow, 'FillRect', restColor, rect)
       Screen('drawtext',mainWindow,'REST',centerX - tempBounds_REST(3)/2,centerY-rectHeight/2 - rectHeight/2,textColor);
        % all trial types will involve the main grey rectangle
        Screen('FillRect', mainWindow,restColor, rect);
    elseif blockType == cfg.HAPPY
        blockTypeStr = 'HAPPY';
        % now check if we're doing rtfmri or no (practice, transfer)
% 
        if runData.rtData
            % udpate display
            % calculate amount to fill in rectangle based on smoothed score
            mostRecentScore = runData.feedbackScoreSmoothed(iTR-1);
            % this makes a rectangle that's in proportion to the score
            feedbackRect = rect;
            feedbackRect(2) = rect(4) - (rect(4) - rect(2))*mostRecentScore;
            Screen('drawtext',mainWindow,'HAPPY',centerX - tempBounds_HAPPY(3)/2,centerY-rectHeight/2 - rectHeight/2,textColor);
            Screen(mainWindow, 'FillRect', restColor, rect)
            Screen('DrawLine',mainWindow, 0,rect(1)-lineW,centerY,rect(3)+lineW,centerY,[7])

            if ~isnan(mostRecentScore)
               % this makes a rectangle that's in proportion to the score
               feedbackRect = rect;
               feedbackRect(2) = rect(4) - (rect(4) - rect(2))*mostRecentScore;
                 if mostRecentScore <= 0.5
                    Screen(mainWindow,'FillRect', badColor, feedbackRect);
                    bonus_points = sprintf('$%2.2f', 0);
                else
                    Screen(mainWindow,'FillRect', maxGreenColor, feedbackRect);
                    bonus_points = sprintf('$%2.2f', mostRecentScore);
                end
                % put bonus score under the rectangle
                runData.FeedbackGiven{iTR} = bonus_points; % what people will see
                tempBounds = Screen('TextBounds', mainWindow, bonus_points);
                Screen('drawtext',mainWindow,bonus_points,centerX - tempBounds(3)/2,feedbackRect(4)+(centerY/10)-tempBounds(4)/2,[0 0 0]);  
            end
        else % if a transfer run, just draw the rectangle
           Screen('drawtext',mainWindow,'HAPPY',centerX - tempBounds_HAPPY(3)/2,centerY-rectHeight/2 - rectHeight/2,textColor);
           Screen(mainWindow, 'FillRect', restColor, rect)
        end
        
    elseif blockType == cfg.MATH 
        blockTypeStr = 'MATH';
        % here we just check for responses and show one number on the
        % screen, having them press for even or odd
        % have a new number flip with every TR
        Screen(mainWindow, 'FillRect', restColor, rect)
        runData.random_number(iTR) = randi(50);
        random_number_string = sprintf('%i', runData.random_number(iTR));
        Screen('drawtext',mainWindow,'MATH',centerX - tempBounds_MATH(3)/2,centerY-rectHeight/2 - rectHeight/2,textColor);
        Screen('drawtext',mainWindow,runData.LEFT_PRESS,centerX - tempBounds_MATH(3)/2 -tempBounds_L(3),centerY-rectHeight/2 - tempBounds_L(4)/2,textColor);
        Screen('drawtext',mainWindow,runData.RIGHT_PRESS,centerX + tempBounds_MATH(3)/2 ,centerY-rectHeight/2 - tempBounds_R(4)/2,textColor);
        tempBounds = Screen('TextBounds', mainWindow, random_number_string);
        Screen('drawtext',mainWindow,random_number_string,centerX -tempBounds(3)/2,centerY - tempBounds(4)/2,textColor);
    end
    % flip for that TR AND check for any key presses during the PREVIOUS
    % TR!
    % so we will store the pulse for the start of the TR
    % and the key presses for the NEXT TR in which they occur
    [timing.trig.pulses(volCounter) runData.pulses(volCounter) timing.leftPressRT(volCounter), timing.rightPressRT(volCounter)] = WaitTRPulse_KbQueue(TRIGGER_keycode,DEVICE,timing.plannedOnsets.TR(iTR));
    % put up a plus for the task start
    timing.actualOnsets.TR(iTR) = Screen('Flip', mainWindow); % show the rectangle once the story starts

    % first flush any previous key presses
    KbQueueFlush(DEVICE);
    % enter any left or right key presses
    if timing.leftPressRT(volCounter) > 0 && iTR > 1
        runData.leftPressRT(iTR-1) = timing.leftPressRT(volCounter);
        runData.leftPress(iTR-1) = 1; % the TR in which the press occurred
        leftPress = 1;
    end
    if timing.rightPressRT(volCounter) > 0 && iTR > 1
        runData.rightPressRT(iTR-1) = timing.rightPressRT(volCounter);
        runData.rightPress(iTR-1) = 1;
        rightPress = 1;
    end

    % now check for any new classification outputs
    if blockType == cfg.HAPPY
        if runData.rtData
            timing.classifierLoadStart(iTR) = GetSecs;
            tOutputFileTimeOut = GetSecs + deltat;
            % look for the TR 2 TR's before the current TR***
            trLook = volCounter - 2;
            trId = sprintf('TR-%03d',trLook); % this is the filenum of the TR 
            while (~runData.OutputFileLoad(iTR) && (GetSecs < tOutputFileTimeOut))
               [runData.OutputFileLoad(iTR), runData.OutputFile{iTR}] = GetSpecificOutputFile(runDir_rtcloud, runId, trId);
            end
            % if file exists, load the score
            if runData.OutputFileLoad(iTR)
               timing.classifierFileFound(iTR) = GetSecs;
               % this is where we load the text file
               psc = load([runDir_rtcloud '/' runData.OutputFile{iTR}]);
               runData.feedbackScore(iTR) = psc;
               % smooth if you can
               if ~isnan(runData.feedbackScoreSmoothed(iTR-2))
                   % we can smooth over 3
                   runData.feedbackScoreSmoothed(iTR) = mean([runData.feedbackScore(iTR-2:iTR)]);
               elseif ~isnan(runData.feedbackScoreSmoothed(iTR-1))
                   % we can smooth over 2
                   runData.feedbackScoreSmoothed(iTR) = mean([runData.feedbackScore(iTR-1:iTR)]);
               else
                   % no smoothing
                   runData.feedbackScoreSmoothed(iTR) = runData.feedbackScore(iTR);
               end
               % now update display
               currentScore = runData.feedbackScoreSmoothed(iTR);
               Screen('drawtext',mainWindow,'HAPPY',centerX - tempBounds_HAPPY(3)/2,centerY-rectHeight/2 - rectHeight/2,textColor);
               Screen(mainWindow, 'FillRect', restColor, rect)
               Screen('DrawLine',mainWindow, 0,rect(1)-lineW,centerY,rect(3)+lineW,centerY,[7])
               % this makes a rectangle that's in proportion to the score
               feedbackRect = rect;
               feedbackRect(2) = rect(4) - (rect(4) - rect(2))*currentScore;
                 if currentScore <= 0.5
                    Screen(mainWindow,'FillRect', badColor, feedbackRect);
                    bonus_points = sprintf('$%2.2f', 0);
                else
                    Screen(mainWindow,'FillRect', maxGreenColor, feedbackRect);
                    bonus_points = sprintf('$%2.2f', currentScore);
                end
                % put bonus score under the rectangle
                runData.FeedbackGiven{iTR} = bonus_points; % what people will see
                tempBounds = Screen('TextBounds', mainWindow, bonus_points);
                Screen('drawtext',mainWindow,bonus_points,centerX - tempBounds(3)/2,feedbackRect(4)+(centerY/10)-tempBounds(4)/2,[0 0 0]);
                timing.startFeedbackDisplay(iTR) = Screen('Flip',mainWindow); % flip as soon as it's ready
            end
        end
    end

    % print out TR information
    fprintf(dataFile,'%-8d%-8s%-8d%-8d%-8.3f%-8d%-8.3f%-8.3f%-8d%-8.3f\n', runNum,blockTypeStr,volCounter,iTR,timing.actualOnsets.TR(iTR)-timing.plannedOnsets.TR(iTR),runData.pulses(volCounter),leftPress,rightPress,runData.OutputFileLoad(iTR),runData.feedbackScoreSmoothed(iTR));
    fprintf('%-8d%-8s%-8d%-8d%-8.3f%-8d%-8.3f%-8.3f%-8d%-8.3f\n', runNum,blockTypeStr,volCounter,iTR,timing.actualOnsets.TR(iTR)-timing.plannedOnsets.TR(iTR),runData.pulses(volCounter),leftPress,rightPress,runData.OutputFileLoad(iTR),runData.feedbackScoreSmoothed(iTR));
end

Screen(mainWindow,'TextSize',textSize);
Screen(mainWindow,'TextFont',textFont);



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
file_name = ['behavior_' runId '_' datestr(now,30) '.mat'];
save(fullfile(runDir_display,file_name),'timing', 'runData');

%% ADD MESSAGE THAT SAYS THEIR TOTAL SCORE HERE!!

sca;
ShowCursor;
ListenChar;
end
