% Purpose: run RealTimeGreenEyesDisplay.m
% This script assigns variables and calls the main script to display.

%% experiment setup parameters
clear all; 

debug = 0;
useButtonBox = 1;
fmri = 1; % whether or not you're in the scanning room
rtData = 1;
%% subject parameters
subjectNum = 102;
subjectName = '0219191_greenEyes';
context = 1;
run = 4;
% subject 1: context 1 1, 2 2
% subject 2: context 2 2, 1 1
%% make call to script

RealTimeGreenEyesDisplay(debug, useButtonBox, fmri, rtData, subjectNum, subjectName, context, run)