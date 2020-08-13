# Realtime fMRI Cloud Framework
This is a generic framework for building real-time fMRI processing pipelines in the cloud.

## How it works
There are three general components:
- **File Server**
  - Watches for new dicom images written by the MRI scanner.
  - Sends the dicom images to the projectInterface in the cloud.
  - Listens for requests from the cloud projectInterface to either read or write files (within restricted directories) on the scanner computer.
- **Project Interface**
  - Runs in the cloud.
  - Provides a user interface to start/stop and configure a run.
  - Is the communication link between the fileServer and the project specific code that runs in the cloud.
- **Project Specific Script**
  - Code specific to the fMRI study being done.
  - Waits for dicom files to arrive, creates a data model, returns classification results to the fileServer for feedback purposes.

![](docs/overview.png)<br>
**Fig 1: Overview of Components**<br>

![](docs/scripts.png)<br>
**Fig2: Overview of Where Scripts Run**<br>

A projectInterface is started on the cloud computer. The projectInterface has a web interface which a browser can connect to and allows configuring and starting a run. The web interface is configured so that the browser start button starts the project specific script. Wherever the projectInterface is installed is where your project specific python script will also run. The projectInterface also serves as the intermediary for communication between the the fileserver (running in the control room) and the project specific script (running in the cloud).

A fileServer is started on the scanner computer that can watch for files within specified directories. The fileServer connects to the projectInterface. The fileServer requires a username and password to connect to and login to the projectInterface.

## Other Links
- [Wrapping Your Experiment Script with the RealTime Framework](docs/how-to-wrap-your-project.md)
- [Running a Realtime Experiment](docs/how-to-run.md)
- [Run Project in a Docker Container](docs/run-in-docker.md)


## Installation

#### Step 1: Install Mini-Conda and NodeJS
*On the cloud computer where processing will take place, do these steps*
1. Check if you have mini-conda already installed. In a terminal run <code>conda -V</code>
    - *Mac Specific:* [Install Mini-Conda](https://docs.conda.io/en/latest/miniconda.html)
    - *Linux Specific:* Install Mini-Conda
        - <code>wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh</code>
        - <code>bash Miniconda3-latest-Linux-x86_64.sh -b</code>
2. Check if you have Node.js and NPM installed. In a terminal run <code>node -v</code> and <code>npm -v</code>
    - *Mac Specific:* Install Node.js
        - Check if Homebrew 'brew' is installed run <code>brew -h</code>
            - [Install Homebrew](https://treehouse.github.io/installation-guides/mac/homebrew) if it is not installed
        - Run <code>brew update</code>
        - Run <code>brew install node</code>
    - *Linux Specific* (CentOS): Install Node.js
        - <code>sudo yum install epel-release</code>
        - <code>sudo yum install nodejs</code>

#### Step 2: Install Realtime ProjectInterface on cloud VM (All OS types)
*On the cloud computer where processing will take place, do these steps*
1. Pull the source code <code>git clone https://github.com/brainiak/rt-cloud.git</code>
2. <code>cd rt-cloud/</code>
3. Get the local ip address *<local_ip_addr>*
    - *Mac Specific:* Google "what's my ip address"
    - *Linux Specific:* <code>hostname -i</code>
4. Make a private key and an ssl certificate or copy an existing one into the certs directory<br>
    - <code>mkdir certs; openssl genrsa -out certs/rtcloud_private.key 2048</code>
    - <code>bash scripts/make-sslcert.sh -ip *[local_ip_addr]*</code>
5. Create the conda environment<br>
    - <code>conda env create -f environment.yml</code>
    - <code>conda activate rtcloud</code>
6. Install node module dependencies<br>
    - <code>cd web; npm install; cd ..</code>
7. Create a user:<br>
    - <code>bash scripts/add-user.sh -u [new_username] -p [password]</code>


#### Step 3: Install FileServer or FeedbackReceiver on Console Computer (All OS Types)
*On the console computer where dicoms are written, do these steps*
1. Repeat Step 1.1 above to install Mini-Conda
2. Clone the rt-cloud code <code>git clone https://github.com/brainiak/rt-cloud.git</code>
3. Copy the ssl certificate created in Step 2.4 above to this computer's rt-cloud/certs directory
    - Copy rt-cloud/certs/rtcloud.crt from the cloud computer
    - Copy it into the rt-cloud/certs directory on the fileServer computer



## Testing the Sample Project
For the sample we will run both the projectInterface and fileServer on the same computer. Follow the above installation steps but install both the fileServer and projectInterface on the same computer. In a production deployment the projectInterface would typically run in a cloud VM and the fileServer would run in the control room console computer.<br>

**Note:** The --test option runs in test mode which doesn't use SSL encryption and accepts a default username and password, both are 'test'. **Never run with the --test option in production.**

1. Open a terminal
    - Start the projectInterface<br>
        - <code>conda activate rtcloud</code>
        - <code>bash scripts/run-projectInterface.sh -p sample --test</code>
2. Open another terminal
    - Start the fileServer<br>
        - <code>conda activate rtcloud</code>
        - <code>bash scripts/run-fileserver.sh -s localhost:8888 --test</code>
3. Optional - Open another terminal to start the feedbackReciever
    - Start the feedbackReceiver<br>
        - <code>conda activate rtcloud</code>
        - <code>python rtCommon/feedbackReceiver.py -s localhost:8888 --test</code>
4. Navigate web browser to URL http://localhost:8888
    - If prompted for username and password enter:<br>
        username 'test', password 'test'
5. Alternate step 4 - Run sample project from the command line connecting to remote fileServer<br>
    <code>python projects/sample/sample.py --filesremote</code>

#### Using the Sample Project with synthetic data generated by BrainIAK
1. Alternate to step 1 above
    - Start the projectInterface<br>
        - <code>conda activate rtcloud</code>
        - <code>bash scripts/run-projectInterface.sh -p sample -c projects/sample/conf/sample-synthetic.toml --test</code> 
2.  Alternate to step 2 above
    - Start the fileServer<br>
        - <code>conda activate rtcloud</code>
        - <code>bash scripts/run-fileserver.sh -s localhost:8888 --allow_synthetic_data --test</code> 
3. Same as step 3 above

## Next Steps
1. Run the sample project without the --test options. This will require the following steps. See [Running a Realtime Experiment](docs/how-to-run.md) for instructions on accomplishing these steps.
    - Add the SSL certificate *rtcloud/certs/rtcloud.crt* that was created in install step 2 above into your web browser.
    - Include the -ip [local_ip_addr] option when starting the projectInterface.
    - Include the -u [username] and -p [password] options when starting the fileServer. Use the username and password created in install step 2 above.
    - Navigate web browser to http**s**://localhost:8888 for a SSL connecton
        - i.e. instead of the non-SSL http:// address used above for testing
    - When prompted for login by Web browser use the username and password created in install step 2 above.
2. Install and run the projectInterface on a remote computer. Run the fileServer on the computer where the dicoms are written.
3. Create your own project python script and wrap it with the real-time framework. See [Wrapping Your Experiment Script with the RealTime Framework](docs/how-to-wrap-your-project.md)

## Further Reading
- [Run Project in a Docker Container](docs/run-in-docker.md)
- [Details](docs/details.md) - coming soon

<details>
<summary>Expand Item</summary>
    More items here
</details>
