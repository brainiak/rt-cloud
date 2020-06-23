

% display parameters
textColor = 0;
textFont = 'Arial';
textSize = 30;
textSpacing = 25;
fixColor = 0;
backColor = 127;
fixationSize = 4;% pixels
minimumDisplay = 0.25;

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

screenNumbers = Screen('Screens');
screenNum = screenNumbers(end);
[screenX screenY] = Screen('WindowSize',screenNum);
% put this back in!!!
windowSize.degrees = [51 30];
resolution = Screen('Resolution', screenNum);
screenX = 1280;
screenY = 720;
%%
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
Screen(mainWindow,'TextFont',textFont);
Screen(mainWindow,'TextSize',circleFontSize); % starts at 30
Screen('DrawLine',mainWindow, 0,rect(1)-lineW,centerY,rect(3)+lineW,centerY,[7]);
Screen(mainWindow,'FillRect',backColor);
bonus_points = sprintf('$%2.2f', 0);
tempBounds = Screen('TextBounds', mainWindow, bonus_points);
feedbackRect = rect;
Screen(mainWindow, 'FillRect', restCircleColor, rect)
%Screen('drawtext',mainWindow,bonus_points,centerX-tempBounds(3)/2,feedbackRect(4)+(centerY/10)-tempBounds(4)/2,[0 0 0]);
Screen('Flip',mainWindow);
%% example if did 100 %
mainWindow = Screen(screenNum,'OpenWindow',backColor,[0 0 screenX screenY]);
Screen(mainWindow,'TextFont',textFont);
Screen(mainWindow,'TextSize',circleFontSize); % starts at 30
this_ev = 1;
Screen('DrawLine',mainWindow, 0,rect(1)-lineW,centerY,rect(3)+lineW,centerY,[7]);
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
tempBounds = Screen('TextBounds', mainWindow, bonus_points);
Screen('drawtext',mainWindow,bonus_points,centerX-tempBounds(3)/2,feedbackRect(4)+(centerY/10)-tempBounds(4)/2,[0 0 0]);
Screen('Flip',mainWindow);
%%
mainWindow = Screen(screenNum,'OpenWindow',backColor,[0 0 screenX screenY]);
Screen(mainWindow,'TextFont',textFont);
Screen(mainWindow,'TextSize',circleFontSize); % starts at 30
Screen('FillRect', mainWindow,recordingCircleColor, rect)
Screen('Flip',mainWindow);