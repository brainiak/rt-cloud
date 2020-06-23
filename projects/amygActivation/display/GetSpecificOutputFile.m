function [fileAvail, specificFile] = GetSpecificOutputFile(classOutputDir,runId,trId)

% update this if you're using a different name
specificFile = ['percentChange_' runId '_' trId '.txt'];
if exist(fullfile(classOutputDir,specificFile),'file')
    fileAvail = 1;
else
    fileAvail = 0;
end