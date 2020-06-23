function [TRnumber] = convertTR(onsetTime,offsetTime,TRlength)

dt = offsetTime - onsetTime;
TRnumber = floor(dt/TRlength)  + 1;

end