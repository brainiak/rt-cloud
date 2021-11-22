# Run Project in a Docker Container

## Allocate a VM in the cloud
If you will run the project on the cloud, the following instructions will help deploy a cloud VM. If you will run the project on local resources skip to the 'Install Docker' section.

- Microsoft Azure instructions:<br>
https://docs.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-portal
- Amazon AWS instructions:<br>
https://aws.amazon.com/getting-started/tutorials/launch-a-virtual-machine/

### Some notes for Azure VM:
- Choose CentOS 7.5 (which the following instructions are based on)
- Create a resource group 'rtcloud' to make it easier to track later
- Choose VM instance type F4s_v2, F8s_v2, or F16s_v2 (depending on number of cores desired)
- Choose premium SSD disk, no need for an extra data disk, but we will extend the main disk to 60 GB after VM creation.
- NIC network security group - choose 'Advanced' to create a network security group. This will allow you later to configure port 8888 as allowed for traffic.
- Choose Auto-shutdown and set a time during the night (in case you forget to power down)


## Install Docker
**Install Docker Engine**

    sudo yum install -y yum-utils device-mapper-persistent-data lvm2
    sudo yum-config-manager -y --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose

**Add your username to the docker group** (to avoid using sudo for docker commands)

    sudo usermod -aG docker <username>
    newgrp docker

**Config Docker to start at boot time**

    sudo systemctl enable docker
    sudo systemctl start docker

**test docker**

    docker run hello-world

## Install rtcloud for Docker
**Pull rtcloud image**

    docker pull brainiak/rtcloud:latest

**Add the rtgroup**<br>
Add a new group with GID 5454 to you local system which matches the user and group ID used in the rtcloud Docker container. Add your username to be a member of the rtgroup.

    sudo groupadd -g 5454 rtgroup
    sudo usermod -a -G rtgroup <your-username>
    sudo chgrp -R rtgroup <projects-dir>

**Create the rtcloud ssl certificate**<br>
This will create a self-signed SSL certificate called **rtcloud.crt** to allow encrypted communication with the projectInterface. You will need to install the rtcloud.crt certificate in your browser for trusted communication. The certificate will be created in location:<br> /var/lib/docker/volumes/certs/\_data/rtcloud.crt

    IP=`curl https://ifconfig.co/`
    docker run -it --rm -v certs:/rt-cloud/certs brainiak/rtcloud:latest scripts/make-sslcert.sh -ip $IP

**Add a user for web interface**<br>
The web connection to the projectInterface requires a user/password to authenticate. You can create a username and password with this command.

    docker run -it --rm -v certs:/rt-cloud/certs brainiak/rtcloud:latest scripts/add-user.sh -u <username>

## Run rtcloud projectInterface
The above installation only needs to be run once, then the projectInterface can be started whenever needed with these commands.

    IP=`curl https://ifconfig.co/`
    PROJ_DIR=<full_path_to_project_dir>
    PROJ_NAME=<name>

    docker run -it --rm -v certs:/rt-cloud/certs -v $PROJ_DIR:/rt-cloud/projects/$PROJ_NAME -p 8888:8888  brainiak/rtcloud:latest scripts/run-projectInterface.sh -p $PROJ_NAME -c projects/$PROJ_NAME/config.toml -ip $IP


## Alternate simpler calls using the run-docker.sh script
The rt-cloud githup repo has a run-docker.sh script that encapsulates the docker specific call parameters in the above calls. This can make it simpler to call the functions you want within the docker image. The following shows the previous commands using the run-docker.sh helper script. Set the $PROJ_DIR env variable before calling run-docker.sh so it can map the project directory into the docker container.

    scripts/run-docker.sh scripts/make-sslcert.sh -ip $IP
    scripts/run-docker.sh scripts/add-user.sh -u <username>
    scripts/run-docker.sh scripts/run-projectInterface.sh -p sample -c projects/sample/conf/sample.toml -ip $IP

## Alternate methods using docker-compose
Docker compose can be used to start a container running with all the appropriate directories and ports mapped, making it easier to issue calls (i.e. run commands) in a continuously running container.

The docker compose file is located at: `rt-cloud/docker/docker-compose.yml`. Edit the docker-compose.yml file and replace `/tmp/myproject` with the path to your project, and update the internal container mount point by replacing 'myproject' in `/rt-cloud/projects/myproject` with your project directory name.

Then start the docker compose container running `docker-compose up`.

    docker-compose -f docker/docker-compose.yml up &

Stop the docker compose container by running `docker-compose down`

    docker-compose -f docker/docker-compose.yml down

The running container will be named `rtserver`. You can then issue commands to the running container such as:

    docker exec -it rtserver ls /rt-cloud/projects

    docker exec -it rtserver scripts/run-projectInterface.sh -p myproject -c /rt-cloud/projects/myproject/config.toml --test

This makes it easier to run commands without specifying volumes and ports to map each time, and is more efficient as it uses a running container rather than starting a new container for each command.

## Docker Image with ANTs, FSL and C3D (brainiak/rtcloudxl)
Thers is a version of the rtcloud docker image that also has ANTs, FSL and C3D installed in the image along with the RT-Cloud framework. It is available as brainiak/rtcloudxl:[release-tag], such as brainiak/rtcloudxl:1.3. This container is significantly larger (about 30 GB uncompressed) than the basic rtcloud image, and so is not listed as the default release of the image.

