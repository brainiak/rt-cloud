**Overview of Real-Time Analysis Pipeline**

One of the key benefits of RT-Cloud is that it makes it possible to use cutting-edge, computationally intensive large-scale AI models to analyze fMRI data in real time. This project demonstrates this point by using RT-Cloud to reconstruct and classify viewed natural scenes from fMRI data in (simulated) real-time. Specifically, this project 1) takes in 7T NIfTI images that were previously collected while participants viewed natural scenes, 2) performs real-time-compatible preprocessing and a real-time-compatible GLM to extract a beta map for each viewed natural scene, and then 3) feeds these beta maps into a MindEye2 machine learning model (previously fine-tuned on this subject’s data) to generate image reconstructions and/or retrievals. Note that the MindEye2 model requires a GPU to run, so this project only works if the data analyzer component of RT-Cloud is hosted on a GPU-enabled processor.

The fMRI data used in this demonstration project were taken from the Natural Scenes Dataset. Here is a description from the dataset’s website:

"The Natural Scenes Dataset (NSD) is a large-scale fMRI dataset conducted at ultra-high-field (7T) strength at the Center of Magnetic Resonance Research (CMRR) at the University of Minnesota. The dataset consists of whole-brain, high-resolution (1.8-mm isotropic, 1.6-s sampling rate) fMRI measurements of 8 healthy adult subjects while they viewed thousands of color natural scenes over the course of 30–40 scan sessions. While viewing these images, subjects were engaged in a continuous recognition task in which they reported whether they had seen each given image at any point in the experiment. These data constitute a massive benchmark dataset for computational models of visual representation and cognition, and can support a wide range of scientific inquiry."

Prior to the (simulated) real-time session, we first pre-trained a MindEye2 model on a GPU with all data from subjects 2 through 8. Then, we fine-tuned the MindEye2 model on subject 1's day 1 data.

Having completed these preliminary steps, we can do (simulated) real-time reconstructions. The real-time analysis pipeline is all contained within the mindeye.py file.

First, NIfTI images at each TR are streamed via the BIDS interface data streamer. In this project, we stream bold images from the first run of subject 1's day 2 session. That is, we fine-tuned on subject 1's day 1 session and we do reconstructions with the fine-tuned model on subject 1's day 2 session.

Second, incoming NIfTI images are fed into a minimal pre-processing pipeline for quick reconstructions. The raw NIfTI images are motion corrected to the first TR of subject 1's day 2 run 1 by the FMRIB Software Library's (FSL) mcflirt function. Next, the motion corrected NIfTI images are aligned with the brain images from subject 1's day 1 session by a call to FSL's flirt function.

Immediately after the last TR of a stimulus trial, a simple Least-Squares Single (LSS) General Linear Model (GLM) is fit onto the cumulative data up until the current TR to acquire beta estimates for each voxel for the stimulus trial. Note that the last TR of a stimulus trial is estimated by assuming a 4.8 s HRF lag (3 TR's of 1.6 s). Furthermore, a TR is considered to be part of a stimulus trial when at least half of its duration is within the stimulus trial. The GLM model is implemented via the python package Nilearn's FirstLevelModel. The beta estimates are masked via a mask that is aligned with subject 1's day 1 session 1 brain and selects for voxels in and around the visual cortex. The masked beta estimates are then passed through the pre-trained and fine-tuned MindEye2 model to acquire image reconstructions and retrievals. The image reconstruction and retrieval process is described at length in the MindEye2 paper.

The mindeye.py file contains all of the code that goes from the streamed raw NIfTI file, to motion correction and alignment via FSL, to betas via Nilearn, and then to generating the images via the PyTorch machine learning library. MindEye2 computations are performed within the do_reconstructions and get_top_retrievals functions of the mindeye.py file. The output of do_reconstructions and get_top_retrievals is immediately sent to the analysis listener computer where it can modify the stimulus shown in PsychoPy in (simulated) real-time.

**How to set up**

1) 80GB of GPU space and 128 GB of CPU space are required for the data analyzer computer. The set up currently is designed for linux 64-bit intel computers and we are working on instructions for Windows and Mac.
2) On a GPU-enabled computer, go to the directory where you want to place the rt-cloud folder with this project inside it, and then download [apptainer](https://apptainer.org/). Next, pull the latest rtcloud docker image into an apptainer file: 
    ```
    apptainer pull docker://brainiak/rtcloud:latest
    ```
    Alternatively, you could get the .sif file, which the above command creates, from the hugging face data set described in set up step (6) below and place the rtcloud_latest.sif file in the directory instead of doing this apptainer pull command.
3) On your local laptop/computer which you are going to display PsychoPy on, do the rt-cloud [local installation](https://github.com/brainiak/rt-cloud/tree/master?tab=readme-ov-file#local-installation) consisting of getting the rtcloud anaconda environment set up and cloning the rt-cloud repository on your local laptop/computer.
4) Download the rt-cloud repository into your GPU-enabled computer like you did locally in (3).
5) Download this /mindeye/ projects folder from the rt-cloud-projects repository and place it in the projects folder of the rt-cloud repository both locally on the PsychoPy display computer and on the GPU-enabled data analyzer computer.
6) Change the absolute_path variable in the rt-cloud/projects/mindeye/psychopy_example/rtcloud_psychopy.py file on your PsychoPy display local computer to the absolute path location of your rt-cloud folder you set up locally in (3).
7) Download the hugging face dataset [here](https://huggingface.co/datasets/rkempner/rt-cloud-mindeye) into your GPU-enabled computer. In the mindeye.py script in this /mindeye/ folder, set the path of data_and_model_storage_path to be where you place this hugging face dataset. 
8) From this /mindeye/ folder, get the bidsRun.py file and replace the bidsRun.py file within rt-cloud/rtCommon on your GPU-enabled computer with this new version of the bidsRun.py file set up particularly for this project.
9) On the GPU-enabled computer, create a conda environment by downloading the rt_mindEye2.yml file from this /mindeye/ folder then run: ```conda env create -f rt_mindEye2.yml```
10) Copy the file called bashrc_mindeye.py from this /mindeye/ folder to rt-cloud/ in the GPU-enabled computer.
11) Copy the BidsDir from the hugging face dataset into rt-cloud/projects/mindeye/ in the GPU-enabled computer.

**How to run**
1) On the GPU-enabled computer,
   - Go to the directory with the rtcloud_latest.sif file created in set up step (2).
   - Enter the apptainer (the --nv flag connects to the gpu)
     ```
     apptainer exec --nv ~/rtcloud_latest.sif bash
     ```
   - cd into the rt-cloud directory
   - Run the bash set up file you created in setup
     ```
     source bashrc_mindeye
     ```
     which will set up fsl and the anaconda environment within the apptainer.
   - Then run the project server/data analyzer
     ```
     bash scripts/data_analyser.sh -p mindeye --port 8898 --subjectRemote --test
     ```
3) Run the following on your local computer to enable port-forwarding between the GPU-enabled computer and your local laptop
   used for the analysis listener, web-interface and PsychoPy task display:
   ```
   ssh -L 8892:hostname:8898 [username]@[server-name]
   ```
   where hostname is the hostname of the GPU-enabled compute node. This is how we allow the data analyzer on the GPU-enabled computer on a server to send information to your local computer via the analysis listener which then becomes input for PsychoPy.
4) In terminal on your PsychoPy display computer locally, cd into the rt-cloud directory from set up (3). Activate the local rtcloud anaconda environment. Run the analysis listener start up:
   ```
   WEB_IP=localhost
   bash scripts/analysis_listener.sh -s $WEB_IP:8892  --test
   ```

5) Open a new terminal locally on your PsychoPy display computer. cd into the rt-cloud directory from set up (3) and then go to the following path: ```projects/mindeye/psychopy_example/```. Activate the rtcloud environment and run ```python rtcloud_psychopy.py```. This will open up the PsychoPy program which starts waiting for incoming output from the data analyzer that reaches your computer through the analysis listener. Output coming in from the real-time analysis of the fMRI data can then modify the stimuli given to your participant through the PsychoPy program. 

6) On your local computer, open the webinterface by going to [http://localhost:8882/](http://localhost:8882/). Then enter "test" for both the username and password and press run. Files will populate the outDir in the local rt-cloud directory via the analysis listener and the PsychoPy program will start displaying images once it receives the first TR's information.

**Example PsychoPy Visuals of Real-Time Visual Image Retrieval**

When you run the project server via the webinterface and run PsychoPy which is waiting for input via the analysis listener, you will get images like below where we can see the actual ground truth image shown to participants compared to the top 5 retrievals. The MindEye2 model's most likely candidate image is directly adjacent to the grouth truth image. The model is retrieving the most likely candidate images from the pool of images given in the 63 stimuli trials in the run.

![Example PsychoPy Display Image:](https://github.com/brainiak/rtcloud-projects/blob/main/mindeye/example_psychopy.png)
**Under Construction**

1) Display reconstructions in (simulated) real-time. 
2) Create an easier set up procedure consisting of a single apptainer file with everything set up already.
3) Improve reconstruction/retrieval peformance by utilizing the enhanced image feature of the MindEye2 model.
4) Improve reconstruction/retrieval performance by improving bold image preprocessing through slice time correction and more sophisticated alignment methods.
5) Create set up instructions for Mac and Windows.
