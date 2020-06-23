function basic_tone(fmri,trigger,duration)

% Perform basic initialization of the sound driver:
InitializePsychSound(1);
freq = 44100;
nrchannels = 2;
snddata = MakeBeep(378, duration, freq);
snddata = [snddata;snddata];

if ~fmri
    pahandle = PsychPortAudio('Open', [], [], [], freq, nrchannels);
else
    DEVICENAME = 'HDA Creative: ALC898 Analog (hw:3,0)';
    devices=PsychPortAudio('GetDevices');
    for dev = 1:length(devices)
        devName = devices(dev).DeviceName;
        if strcmp(devName,DEVICENAME)
            DEVICE = devices(dev).DeviceIndex;
        end
    end
    %%%%%%
    pahandle = PsychPortAudio('Open', DEVICE, [], [], freq, nrchannels);
end
PsychPortAudio('FillBuffer', pahandle, snddata);

% start it immediately
PsychPortAudio('UseSchedule',pahandle,1); 
PsychPortAudio('AddToSchedule',pahandle,0); 
begin_time = PsychPortAudio('Start', pahandle, [], trigger);

PsychPortAudio('Close')
end