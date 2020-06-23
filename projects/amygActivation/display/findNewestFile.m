% find the most recent file in the specified location

function [filetoload] = findNewestFile(filepath,filetodir)
temp = dir(filetodir);
if ~isempty(temp)
    dates = [temp.datenum];
    names = {temp.name};
    [~,newest] = max(dates);
    filetoload = fullfile(filepath, names{newest});
else
    filetoload = [];
end