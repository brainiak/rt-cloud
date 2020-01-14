# The Sample Project

The purpose of this sample project is to familiarize you with the tools that are available to you through our **Realtime fMRI Cloud Framework**. In these scripts, we will walk you through a rudimetary project example where we will:

- Initialize a real-time session
- Run a real-time experiment session:
    - that simulates receiving dicoms<sup>\*</sup> in real-time
    - that converts the dicoms received into nifti files
    - but that *only* does a very simple analysis (obtaining the average activation value across all voxels)
    - that plots the values of interest on the internet browser
- Finalize the real-time session

## What's inside the sample project?
There are six main components to the sample project:
- **`conf` folder**
    - This includes a configuration *toml* file that includes defaults to important variables. For instance, the default for the variable `subjectNum` is 101. Here, we also have the naming pattern used for the dicoms (`001_0000{}_000{}.dcm`). For your experiment, you will have to change the contents of this file to fit your needs.
        - NOTE: Usually, a specific *toml* file is set up for each participant. This is the configuration file that is used across all of the runs. 
- **`dicomDir` folder**
    - Here, you will find 10 raw dicoms that we collected. The purpose of these are purely educational.
    - <sup>\*</sup>We have special permission from the Princeton Institutional Review Board to publicly post the dicoms on this Github repository. 
        - **IMPORTANT:** DO NOT post the raw dicoms for your experiment on Github!!
- **`projectMain` script**
    - This script is called when you ...... THIS IS UNCLEAR TO ME!!!
- **`initialize` script**
    - The purpose of this script is to run certain commands *before* you start your experiment. In this sample project, a temporary `tmp` folder is craeted with sub-directories `console_directory` and `cloud_directory` to illustrate the interaction between the console computer and the cloud. 
- **`sample.py` script**
    - This is the script that actually runs the experiment! All of these scripts are well-documented, especially this one. Take a look at the comments to gain a better understanding of how we do what we do here.
- **`finalize` script**
    - The purpose of this script is to run certain commands *after* you finish running your experiment to finalize things. For instance, you can download files from the cloud to the console computer. You can also delete files from the cloud, which you might want to do for privacy.

## How do I make the sample project work?
1. Follow the [installation instructions](https://github.com/brainiak/rt-cloud#installation) for the realtime fMRI cloud framework

2. Follow the [testing the sample project instructions](https://github.com/brainiak/rt-cloud#testing-the-sample-project) on the main repo page
    NOTE: When you start the fileServer, you need to include a couple more things (refer to documentation about [Running ProjectInterface in the Cloud, section 2](https://github.com/brainiak/rt-cloud/blob/master/docs/how-to-run.md#running-projectinterface-in-the-cloud)) for more details):
        - allowed directories --> you'll have to include the full path to the `sample` directory
        - allowed file extensions --> for the sample project, you'll want to use `.dcm`, `.txt`, and `.mat`

3. When you navigate your web browser to the URL [http://localhost:8888/](http://localhost:8888/), you will see the following page:
![](ReadMe_Images/rtCloudWeb_login.png)
Log in using the username and password you set up during the initial installation.

4. On the web browser, click on **Initialize** in the `Session` tab to run `initialize` python script. 
![](ReadMe_Images/rtCloudWeb_initialize.png)

5. To run the experiment, go to the `Run` tab and click on **Run**.
![](ReadMe_Images/rtCloudWeb_run.png)

6. Once you're done running the sample project, click on **Finalize** in the `Session` tab.
![](ReadMe_Images/rtCloudWeb_finalize.png)

In conjunction to the steps above, we highly encourage you to open the relevant scripts in a code text editor. The scripts are well documented and will hopefully help you understand how things work!

### Where can I find different things?
All of the functions we use within the real-time fMRI cloud framework live in the **rtCommon** folder. There are BLANK scripts that are especially relevant in the sample project:

- **`fileClient` script**
    - The functions enable you to interact with files, from starting a lookout (or watch) for a specific type of file to displaying all of the allowed file types.
- **`projectUtils` script**
    - The functions here allow you to interface between the cloud and the consol computer. For instance, if you want to download files from the cloud there's a function to help you do that here!
- **`readDicom` script**
    - The purpose of these functions is to help you read the dicom files and do anything else (e.g., apply a mask) with them.
