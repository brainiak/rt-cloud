% Purpose: make AFNI time descriptions given timing files

%% SPECIFY THESE THINGS FIRTST
subjectId = 'sub-101';
subjectNum = 101;
bids_id = sprintf('sub-%.3i', subjectNum);

%subjectDay= 2; % PUT 1 OR 2 for FACES ---> day 1 or day 3 of scanning, but day 2 of the faces task
%% MAKE SURE CORTRECT
%% now to through eveyrthing
task_path = '/jukebox/norman/amennen/github/brainiak/rt-cloud/projects/faceMatching/';
%save_path = '/data/jag/cnds/amennen/rtAttenPenn/fmridata/Nifti/derivatives/afni/first_level/timing_files';

filePath = [task_path '/' 'behavDir' '/' bids_id];
% first we need to copy as a text file because importdata doesn't like log files here for some reason
fileToDir = [filePath '/' bids_id  '_Day1_Scanner_ABCD_AB_FaceMatching'];
fileToLoad = findNewestFile(filePath,[fileToDir '*.log']);
unix(sprintf('cp %s.log %s.txt',fileToLoad(1:end-4),fileToLoad(1:end-4)));
fileToLoad = findNewestFile(filePath, [fileToDir '*.txt'])


if ~isempty(fileToLoad)
    d = importdata(fileToLoad);
else
    error('Wrong file name!!!');
end

%% first just get all timing
tr = 1.5;
nVols=2;
toDel = tr * nVols;
trigger_str = 'Keypress: equal';
start_str = 'Keypress: q';
trial = 'New trial';
nentries = size(d,1);
trial_startA = [];
trial_startB = [];
condition_A = [];
condition_B = [];
LOOKFORTRIGA = 1;
LOOKFORTRIGB = 1;
for e=1:nentries
    thisrow = d{e};
    if LOOKFORTRIGA
        if ~isempty(strfind(thisrow, trigger_str)) % first trigger
            split_row = strsplit(thisrow, ' ');
            trig_timeA = str2num(split_row{1});
            LOOKFORTRIGA = 0;
        end
    end
    % now get every trial start
    if ~isempty(strfind(thisrow, trial))
        split_row = strsplit(thisrow, ' ');
        AB = split_row{8};
        
        
        if ~isempty(strfind(AB,'A')) % then in the A run
            trial_startA(end+1) = str2num(split_row{1});
        end
    end
end

%%

%save_file_path = [save_path '/' bids_id '/' ses_id ];
%if ~exist(save_file_path)
%    mkdir(save_file_path);
%end;

% instead of doing separete runs, analyze runs togethet

Aind=0;
Bind=0;
n_neutral_A = 0;
n_object_A = 0;
n_happy_A = 0;
n_fearful_A = 0;

NEUTRAL = 1;
OBJECT = 2;
HAPPY = 3;
FEARFUL = 4;
nTRs = 196 - nVols; % how many TRs to keep
nCategories = 4;
REGRESSOR_MATRIX = zeros(nCategories,nTRs)



trigger_str = 'Keypress: 5';
start_str = 'Keypress: q';
trial = 'New trial';
nentries = size(d,1);
condition_A = [];
condition_B = [];
LOOKFORTRIGA = 1;
LOOKFORTRIGB = 1;
for e=1:nentries
    thisrow = d{e};
    if LOOKFORTRIGA
        if ~isempty(strfind(thisrow, trigger_str)) % first trigger
            split_row = strsplit(thisrow, ' ');
            trig_timeA = str2num(split_row{1});
            LOOKFORTRIGA = 0;
        end
    end
    if ~isempty(strfind(thisrow, start_str)) && ~LOOKFORTRIGA
        frontind = 0;
        while LOOKFORTRIGB
            frontind = frontind + 1;
            frontrow = d{e+frontind};
            if ~isempty(strfind(frontrow,trigger_str))
                split_row = strsplit(frontrow, ' ');
                trig_timeB = str2num(split_row{1});
                LOOKFORTRIGB = 0;
            end
        end
    end
    % now get every trial start
    if ~isempty(strfind(thisrow, trial))
        split_row = strsplit(thisrow, ' ');
        AB = split_row{8};
        condition_str = split_row{18};
        if strfind(condition_str, 'Neutral')
            cond=1;
        elseif strfind(condition_str, 'Fixation')
            cond=5;
        elseif strfind(condition_str, 'Happy')
            cond=3;
        elseif strfind(condition_str, 'Fearful')
            cond=4;
        elseif strfind(condition_str, 'Object')
            cond=2;
        end
        
        if ~isempty(strfind(AB,'A')) % then in the A run
            Aind = Aind + 1;
            if Aind < 90
                actual_timing = trial_startA(Aind+1) - trial_startA(Aind);
            else
                % have to look for when it said wait
%                 keep_looking_for_a_stop=1;
%                 nr=e+1;
%                 while keep_looking_for_a_stop
%                     thisnewrow = d{nr};
%                     if ~isempty(strfind(thisnewrow, 'Waiting for the experimenter.'))
%                         split_row = strsplit(thisnewrow, ' ');
%                         tstop = split_row{1};
%                         keep_looking_for_a_stop=0;
%                     end
%                     nr = nr + 1;
%                 end
                %actual_timing = str2num(tstop) - trial_startA(Aind);
                actual_timing=3;
            end
            real_start = trial_startA(Aind) - trig_timeA - toDel;
            TRnumber = convertTR(trig_timeA,trial_startA(Aind),tr) - nVols
            %trial_startA(end+1) = str2num(split_row{1});
            % want: print ONLY start times of each trial
            % the A run should be row 1 and the B run should be row 2
            if cond==1
                % Neutral
                n_neutral_A = n_neutral_A + 1;
                %A_times(NEUTRAL,n_neutral_A) = real_start;
                REGRESSOR_MATRIX(NEUTRAL,TRnumber:TRnumber+1) = 1;
                %fprintf(fileID_A1,'%8.4f\t%6.4f\t1\n', real_start,actual_timing);
            elseif cond==2
                % OBJECT
                n_object_A = n_object_A + 1;
                %A_times(OBJECT,n_object_A) = real_start;
                REGRESSOR_MATRIX(OBJECT,TRnumber:TRnumber+1) = 1;
                %fprintf(fileID_A2,'%8.4f\t%6.4f\t1\n', real_start,actual_timing);
            elseif cond==3
                %fprintf(fileID_A3,'%8.4f\t%6.4f\t1\n', real_start,actual_timing);
                n_happy_A = n_happy_A + 1;
                %A_times(HAPPY,n_happy_A) = real_start;
                REGRESSOR_MATRIX(HAPPY,TRnumber:TRnumber+1) = 1;
            elseif cond==4
                %fprintf(fileID_A4,'%8.4f\t%6.4f\t1\n', real_start,actual_timing);
                n_fearful_A = n_fearful_A + 1;
                %A_times(FEARFUL,n_fearful_A) = real_start;
                REGRESSOR_MATRIX(FEARFUL,TRnumber:TRnumber+1) = 1;
            elseif cond==5
                %fprintf(fileID_A5,'%8.4f\t%6.4f\t1\n', real_start,actual_timing);
            end
            %fprintf('trial %i\t cond %i\t%8.4f\t%6.4f\t1\n', Aind,cond, real_start,actual_timing);

        % now get timing--look to next file
    end
end
end
% should be 18/stim

file_to_save = [filePath '/' 'Regressors_unshifted_Rm2TR.mat'];
save(file_to_save, 'REGRESSOR_MATRIX')