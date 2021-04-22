# **Using the BIDS Data Standard with RT-Cloud**

*Note: Some of this documentation is taken from Polcyn, S. (2021) "Efficient Data Structures for
Integrating the Brain Imaging Data Structure with RT-Cloud, a Real-Time fMRI
Cloud Platform" [Unpublished senior thesis].*

## **BIDS Introduction**

BIDS is the leading data standard for neuroscience data. It is supported by a
wide variety of data formatting and analysis tools, is used by a large and
growing repository of neuroscience datasets called
[OpenNeuro](https://openneuro.org/), has an automated and comprehensive
validation tool that analyzes datasets for compliance and identifies issues, the
[BIDS Validator](https://github.com/bids-standard/bids-validator), and also is
the data format used by a large set of [BIDS
Apps](https://bids-apps.neuroimaging.io/), which are container-based
applications with a standardized interface that work on BIDS-formatted datasets.
The BIDS standard defines the BIDS archive format, which is the format that BIDS
datasets on disk must conform to.

### **The BIDS Archive**

A BIDS archive is a collection of brain activity image and metadata files,
organized in accordance with the BIDS standard. While an in-depth understanding
of the BIDS standard can be obtained from the full standard, viewable online at
https://bids-specification.readthedocs.io/en/stable/, a few key details are as
follows:

1.  **Brain imaging data is stored in the Neuroimaging Informatics
    Technology Initative (NIfTI) format.** NIfTI is a binary file format
    that starts with a header holding basic information about the brain
    data contained in the file. The header is followed by the raw brain
    data. A NIfTI volume's data typically has 4 dimensions, *x, y, z*
    and *t (time)*, so a NIfTI file can be thought of as containing a
    sequence of *t*, 3-D images, each of which has dimensions
    `x * y * z`.

2.  **Metadata is stored in files separate from the image data.** Unlike
    the DICOM image format, the NIfTI image format doesn't store much
    metadata about the image it contains. Accordingly, in the BIDS data
    format, the majority of the metadata about the image and the
    conditions under which it was collected is stored in separate files,
    typically in the JavaScript Object Notation (JSON) or Tab-Separated
    Value (TSV) format.

3.  **Files are named using BIDS entities.** The name of a file in a
    BIDS archive follows a standard format, and it is composed of a set
    of 'entities' (like 'sub' or 'run', corresponding to 'subject' and
    'run', respectively) that signify what the data in the file
    corresponds to. For example, the filename
    "sub-01_task-language_run-1_bold.nii" has 4 BIDS entities, separated
    by underscores ('\_'). The 4 entities and their corresponding values
    are:

    1.  'sub': 01 (this file has data for the subject with ID 01)

    2.  'run': 1 (this file has data from the 1st run)

    3.  'task': language (this file has data from the 'language' task)

    4.  'bold': No value (The presence of the entity is enough to state
        the file holds fMRI brain-oxygen-level-dependent (BOLD) data)

In summary, a BIDS archive is a collection of image and metadata files,
all named using BIDS entities that correspond to the conditions under
which the data or metadata was collected.

### BIDS Apps

BIDS Apps are containerized applications that operate on BIDS datasets and
provide a consistent command-line interface to users. Since each app operates on
a BIDS archive, a full analysis pipeline can potentially be created from
independent BIDS App containers, so components can be easily added, removed, or
modified as needs evolve over time.

## **Why Use BIDS with RT-Cloud**

### BIDS Apps
Using BIDS with RT-Cloud connects you to the BIDS Apps ecosystem, so you
can integrate existing and future BIDS Apps with your real-time fMRI analysis
pipeline, minimizing time spent on setting up computational infrastructure.

### Benefits of BIDS Data Standardization
Storing data in a standardized format brings a host of benefits, the following
of which were adapted from [here](https://bids.neuroimaging.io/benefits).

One major benefit is you and all lab members or clinical team members, once
having learned the standard, know immediately how to navigate both new and old
datasets. Without a standardized format, different team members may format their
data in different ways, forcing you to waste time learning a myriad of data
formats and creating significant problems when a team member leaves the
organization and can no longer explain to new or existing team members how their
dataset format works.  Additionally, external collaborators at other
institutions can easily work on your dataset if everyone uses the same standard.

Another major benefit is future software packages are likely to grow around this
standard. Thus, you can use any of a wide variety of software packages with your
new and existing BIDS datasets that conform to the standard and not spend time
learning additional software-specific formats or be locked-in to a particular
software package.

Finally, if you are required to publish your datasets as a condition of
manuscript publication, having data in a standardized format from the beginning
enables a seamless upload and review process.

## **How to Incorporate BIDS into your RT-Cloud project**
Details of using in a project

Instructions and link to tutorial

## **Replaying Data from OpenNeuro**
Details and example
