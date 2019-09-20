#!/usr/bin/env bash

sudo yum install screen -y
sudo yum update -y

# Install git
if [[ `command -v git` == "" ]]; then
  if [[ "$OSTYPE" == "linux-gnu" ]]; then
    os=`cat /etc/*release | grep ^NAME`
    if echo $os | grep Ubuntu; then
      sudo apt install -y git
    elif echo $os | grep CentOS; then
      sudo yum install -y git
    elif echo $os | grep "Red Hat"; then
      sudo yum install -y git
    fi
  elif [[ "$OSTYPE" == "darwin"* ]]; then
    # Assumes user has brew
    brew install git
  fi
else
  echo "Git already installed"
fi

if [[ `command -v conda` == "" ]]; then
    echo "INSTALL MINICONDA"
    if [ ! -e  ~/Downloads ]; then
        echo "Make direcorty ~/Downloads"
        mkdir ~/Downloads
    fi
    pushd ~/Downloads
    if [[ $OSTYPE == linux* ]]; then
        echo "Install Miniconda on Linux"
        wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh
        bash Miniconda3-latest-Linux-x86_64.sh -b
        echo export PATH="$HOME/miniconda3/bin:\$PATH" >> ~/.bashrc
        echo ". $HOME/miniconda3/etc/profile.d/conda.sh" >> ~/.bashrc
        source ~/.bashrc
    elif [[ $OSTYPE == darwin* ]]; then
        echo "Install Miniconda on MacOSX"
        brew install wget
        wget https://repo.continuum.io/miniconda/Miniconda3-latest-MacOSX-x86_64.sh
        bash Miniconda3-latest-MacOSX-x86_64.sh -b
        echo export PATH="$HOME/miniconda3/bin:\$PATH" >> ~/.bash_profile
        echo ". $HOME/miniconda3/etc/profile.d/conda.sh" >> ~/.bash_profile
        source ~/.bash_profile
    else
        echo "Unrecognized OS Type $OSTYPE"
        exit -1
    fi
    popd
else
    echo "Miniconda already installed"
fi
conda update -y conda
# create the rtcloud conda environment
conda env create -f environment.yml && \
cd web; npm install; cd ..

# Install ANTs without building
wget https://sourceforge.net/projects/advants/files/ANTS/ANTS_Latest/ANTs-2.1.0-rc3-Linux.tar.gz/download -O ANTs-2.1.0-rc3-Linux.tar.gz
tar xzvf ANTs-2.1.0-rc3-Linux.tar.gz
sudo mv ANTs-2.1.0-Linux /opt/
echo 'export PATH=${PATH}:/opt/ANTs-2.1.0-Linux/bin' >> ~/.bash_profile

# Install FSL (to /opt/fsl)
wget https://fsl.fmrib.ox.ac.uk/fsldownloads/fslinstaller.py
sudo yum -y install libpng12 libmng  # needed by FSL
sudo /usr/bin/python2.7 fslinstaller.py -d /opt/fsl --quiet

# Install c3d tool
wget https://sourceforge.net/projects/c3d/files/c3d/Nightly/c3d-nightly-Linux-gcc64.tar.gz/download -O c3d-nightly-Linux-gcc64.tar.gz
tar xzvf c3d-nightly-Linux-gcc64.tar.gz
sudo mv c3d-1.1.0-Linux-gcc64 /opt/
echo 'export PATH=${PATH}:/opt/c3d-1.1.0-Linux-gcc64/bin' >> ~/.bash_profile

BUILD_ANTS=false
if $BUILD_ANTS; then
  #For now assuming Centos
  # Install ANTS
  sudo yum group install -y "Development Tools"
  sudo yum -y install bzip2 wget gcc gcc-c++ gmp-devel mpfr-devel libmpc-devel zlib-devel
  sudo yum install centos-release-scl
  sudo yum -y install devtoolset-7

  cd Downloads
  # Build the ANTs from source
  # Need newer version of cmake than default on Centos 7
  wget https://github.com/Kitware/CMake/releases/download/v3.14.3/cmake-3.14.3.tar.gz
  tar xzvf cmake-3.14.3.tar.gz
  cd cmake-3.14.3/
  ./configure --prefix=/opt/cmake
  make
  sudo make install
  cd ..
  # Complie ANTs
  wget https://github.com/stnava/ANTs/tarball/master -O ants.tgz
  tar xzvf ants.tgz
  mkdir -p /opt/ants
  cd /opt/ants
  scl enable devtoolset-7 bash
  CC=`which gcc` CXX=`which g++` /opt/cmake/bin/cmake ~/Downloads/ANTsX-ANTs*
  CC=`which gcc` CXX=`which g++` make -j 2
  echo 'export PATH=${PATH}:/opt/ants/bin' >> ~/.bashrc
  echo 'export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=4' >> ~/.bash_profile
fi
