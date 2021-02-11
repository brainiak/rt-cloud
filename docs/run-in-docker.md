# Run Project in a Docker Container

## Allocate a VM in the cloud
If you will run the project on the cloud, the following instructions will help deploy a cloud VM. If you will run the project on local resources skip to the 'Install Docker' section.

- Microsoft Azure instructions:<br>
https://docs.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-portal
- Amazon AWS instructions:<br>
https://aws.amazon.com/getting-started/tutorials/launch-a-virtual-machine/

#### Some notes for Azure VM:
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
    sudo yum install -y docker-ce docker-ce-cli containerd.io

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

    docker pull brainiak/rtcloud:1.0

**Add the rtgroup**<br>
Add a new group with GID 5454 which matches the user and group ID used in the rtcloud Docker container. Add you username to be a member of the rtgroup.

    sudo groupadd -g 5454 rtgroup
    sudo usermod -a -G rtgroup <username>
    sudo chgrp -R rtgroup <projects-dir>

**Create the rtcloud ssl certificate**<br>
This will create a self-signed SSL certificate called **rtcloud.crt** to allow encrypted communication with the projectInterface. You will need to install the rtcloud.crt certificate in your browser for trusted communication. The certificate will be created in location:<br> /var/lib/docker/volumes/certs/\_data/rtcloud.crt

    IP=`curl https://ifconfig.co/`
    docker run --rm -v certs:/rt-cloud/certs brainiak/rtcloud:1.0 scripts/make-sslcert.sh -ip $IP

**Add user for web interface**<br>
The web connection to projectInterface requires a user/password to authenticate. You can create a username and password with this command.

    docker run -it --rm -v certs:/rt-cloud/certs brainiak/rtcloud:1.0 scripts/add-user.sh -u <username>

## Run rtcloud projectInterface
Once the above installation only needs to be run once, then the projectInterface can be started whenever needed with these commands.

    IP=`curl https://ifconfig.co/`
    PROJS_DIR=<full_path_to_projects_dir>

    docker run -it --rm -v certs:/rt-cloud/certs -v $PROJS_DIR:/rt-cloud/projects -p 8888:8888  brainiak/rtcloud:1.0 scripts/run-projectInterface.sh -p sample -c projects/sample/conf/sample.toml -ip $IP

## Alternate simpler calls using the run-docker.sh script
The rt-cloud githup repo has a run-docker.sh script that encapsulates the docker specific call parameters in the above calls. This can make it simpler to call the functions you want within the docker image. The following show the previous commands using the run-docker.sh helper script.

    scripts/run-docker.sh scripts/make-sslcert.sh -ip $IP
    scripts/run-docker.sh scripts/add-user.sh -u <username>
    scripts/run-docker.sh scripts/run-projectInterface.sh -p sample -c projects/sample/conf/sample.toml -ip $IP
