toml_file =  % ENTER THE FULL PATH TO THE TOML FILE YOU'RE USING 
dbstop if error;
%toml_file = '/Data1/code/rt-cloud/projects/greenEyes/conf/greenEyes_organized.toml';
runNum = 1;
% if you want it to just be a transfer run w/o neurofeedback, change the
% parameter in the toml file: [display] --> rtData
RealTimeAmygActivation_CLOUD(toml_file, runNum)
