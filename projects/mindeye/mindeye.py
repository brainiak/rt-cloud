# drift correct, normalize, no slice time

# set up main path where everything will be you should download the
# hugging face directory described in readme and put it here on the same
# server where the data analyzer is run so that the data analyzer code with 
# the GPU can access these files
# You should replace the below path with your location
data_and_model_storage_path = '/home/ri4541@pu.win.princeton.edu/rt_mindeye/rt_all_data'
"""-----------------------------------------------------------------------------
Imports and set up for mindEye
-----------------------------------------------------------------------------"""
import os
import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
import shutil
import json
import argparse
import numpy as np
import math
import time
import random
import string
import h5py
from scipy import stats
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
from torchvision import transforms
from accelerate import Accelerator, DeepSpeedPlugin
# SDXL unCLIP requires code from https://github.com/Stability-AI/generative-models/tree/main
sys.path.append('projects/mindeye/generative_models/')
import sgm
from generative_models.sgm.modules.encoders.modules import FrozenOpenCLIPImageEmbedder, FrozenOpenCLIPEmbedder2
from generative_models.sgm.models.diffusion import DiffusionEngine
from generative_models.sgm.util import append_dims
from omegaconf import OmegaConf
from PIL import Image
# tf32 data type is faster than standard float32
torch.backends.cuda.matmul.allow_tf32 = True
# custom functions #
import utils_mindeye
from models import *
import pandas as pd
import ants
import nilearn
import pdb
from nilearn.plotting import plot_design_matrix
import json
import os
import pickle
from collections import defaultdict
import pickle
import pdb
import imageio.v2 as imageio

"""-----------------------------------------------------------------------------
Imports for rtcloud
-----------------------------------------------------------------------------"""
import os
import sys
import argparse
import json
import tempfile
import time
import nibabel as nib
import pandas as pd
import numpy as np
from subprocess import call
from pathlib import Path
from datetime import datetime, date
from scipy.stats import zscore
from nilearn.signal import clean
import pdb
from nilearn.glm.first_level import FirstLevelModel
from nilearn.image import get_data, index_img, concat_imgs, new_img_like
cwd = os.getcwd()
print("cwd ", cwd)
print(os.listdir("projects/mindeye/BidsDir/"))
sys.path.append(cwd)
from rtCommon.utils import loadConfigFile, stringPartialFormat
from rtCommon.clientInterface import ClientInterface
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsRun import BidsRun
from rtCommon.bidsInterface import *

conf_path = 'projects/mindeye/conf/config.json'
try:
    with open(conf_path, 'r') as f:
        config = json.load(f)
    storage_path = config['storage_path']
    data_path = config['data_path']
    derivatives_path = config['derivatives_path']
    fsl_path = config['fsl_path']
    assert os.path.exists(storage_path), "The specified data and model storage path does not exist."
    assert os.path.exists(data_path), "The specified BOLD path does not exist."
    assert os.path.exists(derivatives_path), "The specified derivatives path does not exist."
    assert os.path.exists(fsl_path), "The specified FSL path does not exist."
except FileNotFoundError:
    raise FileNotFoundError("config.json file not found. Please create it with the required paths.")

print(f"Using storage path: {storage_path}")

### Multi-GPU config ###
local_rank = os.getenv('RANK')
if local_rank is None: 
    local_rank = 0
else:
    local_rank = int(local_rank)
accelerator = Accelerator(split_batches=False, mixed_precision="fp16")
device = accelerator.device

cache_dir= f"{data_and_model_storage_path}/cache"
model_name="sub-005_all_task-C_bs24_MST_rishab_MSTsplit_union_mask_finetune_0"
subj=1
hidden_dim=1024
blurry_recon = False
n_blocks=4 
seq_len = 1
with open(f"{data_and_model_storage_path}/clip_img_embedder", "rb") as input_file:
    clip_img_embedder = pickle.load(input_file)
clip_img_embedder.to(device)
clip_seq_dim = 256
clip_emb_dim = 1664


class MindEyeModule(nn.Module):
    def __init__(self):
        super(MindEyeModule, self).__init__()
    def forward(self, x):
        return x
        
model = MindEyeModule()

class RidgeRegression(torch.nn.Module):
    # make sure to add weight_decay when initializing optimizer
    def __init__(self, input_sizes, out_features, seq_len): 
        super(RidgeRegression, self).__init__()
        self.out_features = out_features
        self.linears = torch.nn.ModuleList([
                torch.nn.Linear(input_size, out_features) for input_size in input_sizes
            ])
    def forward(self, x, subj_idx):
        out = torch.cat([self.linears[subj_idx](x[:,seq]).unsqueeze(1) for seq in range(seq_len)], dim=1)
        return out
num_voxels = 8627
model.ridge = RidgeRegression([num_voxels], out_features=hidden_dim, seq_len=seq_len)

class BrainNetwork(nn.Module):
    def __init__(self, h=4096, in_dim=15724, out_dim=768, seq_len=2, n_blocks=n_blocks, drop=.15, 
                clip_size=768):
        super().__init__()
        self.seq_len = seq_len
        self.h = h
        self.clip_size = clip_size
        
        self.mixer_blocks1 = nn.ModuleList([
            self.mixer_block1(h, drop) for _ in range(n_blocks)
        ])
        self.mixer_blocks2 = nn.ModuleList([
            self.mixer_block2(seq_len, drop) for _ in range(n_blocks)
        ])
        
        # Output linear layer
        self.backbone_linear = nn.Linear(h * seq_len, out_dim, bias=True) 
        self.clip_proj = self.projector(clip_size, clip_size, h=clip_size)
    
            
    def projector(self, in_dim, out_dim, h=2048):
        return nn.Sequential(
            nn.LayerNorm(in_dim),
            nn.GELU(),
            nn.Linear(in_dim, h),
            nn.LayerNorm(h),
            nn.GELU(),
            nn.Linear(h, h),
            nn.LayerNorm(h),
            nn.GELU(),
            nn.Linear(h, out_dim)
        )
    
    def mlp(self, in_dim, out_dim, drop):
        return nn.Sequential(
            nn.Linear(in_dim, out_dim),
            nn.GELU(),
            nn.Dropout(drop),
            nn.Linear(out_dim, out_dim),
        )
    
    def mixer_block1(self, h, drop):
        return nn.Sequential(
            nn.LayerNorm(h),
            self.mlp(h, h, drop),  # Token mixing
        )

    def mixer_block2(self, seq_len, drop):
        return nn.Sequential(
            nn.LayerNorm(seq_len),
            self.mlp(seq_len, seq_len, drop)  # Channel mixing
        )
        
    def forward(self, x):
        # make empty tensors
        c,b,t = torch.Tensor([0.]), torch.Tensor([[0.],[0.]]), torch.Tensor([0.])
        
        # Mixer blocks
        residual1 = x
        residual2 = x.permute(0,2,1)
        for block1, block2 in zip(self.mixer_blocks1,self.mixer_blocks2):
            x = block1(x) + residual1
            residual1 = x
            x = x.permute(0,2,1)
            
            x = block2(x) + residual2
            residual2 = x
            x = x.permute(0,2,1)
            
        x = x.reshape(x.size(0), -1)
        backbone = self.backbone_linear(x).reshape(len(x), -1, self.clip_size)
        c = self.clip_proj(backbone)
        
        return backbone, c, b

model.backbone = BrainNetwork(h=hidden_dim, in_dim=hidden_dim, seq_len=seq_len, 
                        clip_size=clip_emb_dim, out_dim=clip_emb_dim*clip_seq_dim) 
utils_mindeye.count_params(model.ridge)
utils_mindeye.count_params(model.backbone)
utils_mindeye.count_params(model)

# setup diffusion prior network
out_dim = clip_emb_dim
depth = 6
dim_head = 52
heads = clip_emb_dim//52 # heads * dim_head = clip_emb_dim
timesteps = 100

prior_network = PriorNetwork(
        dim=out_dim,
        depth=depth,
        dim_head=dim_head,
        heads=heads,
        causal=False,
        num_tokens = clip_seq_dim,
        learned_query_mode="pos_emb"
    )

model.diffusion_prior = BrainDiffusionPrior(
    net=prior_network,
    image_embed_dim=out_dim,
    condition_on_text_encodings=False,
    timesteps=timesteps,
    cond_drop_prob=0.2,
    image_embed_scale=None,
)
model.to(device)

utils_mindeye.count_params(model.diffusion_prior)
utils_mindeye.count_params(model)

# Load pretrained model ckpt
# Replace with pre_trained_fine_tuned_model.pth
tag='sub-005_all_task-C_bs24_MST_rishab_MSTsplit_union_mask_finetune_0.pth'
outdir = f'{data_path}/model'
# print(f"\n---loading {outdir}/{tag}.pth ckpt---\n")
checkpoint = torch.load(outdir+f'/{tag}', map_location='cpu')
state_dict = checkpoint['model_state_dict']
# pdb.set_trace()
model.load_state_dict(state_dict, strict=True)
del checkpoint
# print("ckpt loaded!")

# prep unCLIP
config = OmegaConf.load("projects/mindeye/generative_models/configs/unclip6.yaml")
config = OmegaConf.to_container(config, resolve=True)
unclip_params = config["model"]["params"]
network_config = unclip_params["network_config"]
denoiser_config = unclip_params["denoiser_config"]
# first_stage_config = unclip_params["first_stage_config"]
conditioner_config = unclip_params["conditioner_config"]
sampler_config = unclip_params["sampler_config"]
scale_factor = unclip_params["scale_factor"]
disable_first_stage_autocast = unclip_params["disable_first_stage_autocast"]
offset_noise_level = unclip_params["loss_fn_config"]["params"]["offset_noise_level"]
# first_stage_config['target'] = 'sgm.models.autoencoder.AutoencoderKL'
sampler_config['params']['num_steps'] = 38
with open(f"{data_and_model_storage_path}/diffusion_engine", "rb") as input_file:
    diffusion_engine = pickle.load(input_file)
# set to inference
diffusion_engine.eval().requires_grad_(False)
diffusion_engine.to(device)
ckpt_path = f'{cache_dir}/unclip6_epoch0_step110000.ckpt'
ckpt = torch.load(ckpt_path, map_location='cpu')
diffusion_engine.load_state_dict(ckpt['state_dict'])
batch={"jpg": torch.randn(1,3,1,1).to(device), # jpg doesnt get used, it's just a placeholder
    "original_size_as_tuple": torch.ones(1, 2).to(device) * 768,
    "crop_coords_top_left": torch.zeros(1, 2).to(device)}
out = diffusion_engine.conditioner(batch)
vector_suffix = out["vector"].to(device)
f = h5py.File(f'{data_and_model_storage_path}/coco_images_224_float16.hdf5', 'r')
images = f['images']

sub = "sub-005"
session = "ses-03"
task = 'C'  # 'study' or 'A'; used to search for functional run in bids format
func_task_name = 'C'  # 'study' or 'A'; used to search for functional run in bids format
n_runs = 11

ses_list = [session]
design_ses_list = [session]
    
task_name = f"_task-{task}" if task != 'study' else ''
designdir = f"{data_path}/events"

data, starts, images, is_new_run, image_names, unique_images, len_unique_images = utils_mindeye.load_design_files(
    sub=sub,
    session=session,
    func_task_name=task,
    designdir=designdir,
    design_ses_list=design_ses_list
)

if sub == 'sub-001':
    if session == 'ses-01':
        assert image_names[0] == 'images/image_686_seed_1.png'
    elif session in ('ses-02', 'all'):
        assert image_names[0] == 'all_stimuli/special515/special_40840.jpg'
    elif session == 'ses-03':
        assert image_names[0] == 'all_stimuli/special515/special_69839.jpg'
    elif session == 'ses-04':
        assert image_names[0] == 'all_stimuli/rtmindeye_stimuli/image_686_seed_1.png'
elif sub == 'sub-003':
    assert image_names[0] == 'all_stimuli/rtmindeye_stimuli/image_686_seed_1.png'

unique_images = np.unique(image_names.astype(str))
unique_images = unique_images[(unique_images!="nan")]
len_unique_images = len(unique_images)
print("n_runs",n_runs)

if (sub == 'sub-001' and session == 'ses-04') or (sub == 'sub-003' and session == 'ses-01'):
    assert len(unique_images) == 851

print(image_names[:4])
print(starts[:4])
print(is_new_run[:4])

image_idx = np.array([])  # contains the unique index of each presented image
vox_image_names = np.array([])  # contains the names of the images corresponding to image_idx
all_MST_images = dict()
for i, im in enumerate(image_names):
    # skip if blank, nan
    if im == "blank.jpg":
        i+=1
        continue
    if str(im) == "nan":
        i+=1
        continue
    vox_image_names = np.append(vox_image_names, im)
            
    image_idx_ = np.where(im==unique_images)[0].item()
    image_idx = np.append(image_idx, image_idx_)
    
    all_MST_images[i] = im
    i+=1
    
image_idx = torch.Tensor(image_idx).long()
# for im in new_image_names[MST_images]:
#     assert 'MST_pairs' in im
# assert len(all_MST_images) == 300

unique_MST_images = np.unique(list(all_MST_images.values())) 

MST_ID = np.array([], dtype=int)

vox_idx = np.array([], dtype=int)
j=0  # this is a counter keeping track of the remove_random_n used later to index vox based on the removed images; unused otherwise
for i, im in enumerate(image_names):  # need unique_MST_images to be defined, so repeating the same loop structure
    # skip if blank, nan
    if im == "blank.jpg":
        i+=1
        continue
    if str(im) == "nan":
        i+=1
        continue
    j+=1
    curr = np.where(im == unique_MST_images)
    # print(curr)
    if curr[0].size == 0:
        MST_ID = np.append(MST_ID, np.array(len(unique_MST_images)))  # add a value that should be out of range based on the for loop, will index it out later
    else:
        MST_ID = np.append(MST_ID, curr)
        
assert len(MST_ID) == len(image_idx)
print(MST_ID.shape)
assert len(all_MST_images) == 693

resize_transform = transforms.Resize((224, 224))
MST_images = []
images = None
for im_name in tqdm(image_idx):
    image_file = f"{unique_images[im_name]}"
    im = imageio.imread(f"{data_path}/{image_file}")
    im = torch.Tensor(im / 255).permute(2,0,1)
    im = resize_transform(im.unsqueeze(0))
    if images is None:
        images = im
    else:
        images = torch.vstack((images, im))
    if ("MST_pairs" in image_file): # ("_seed_" not in unique_images[im_name]) and (unique_images[im_name] != "blank.jpg") 
        MST_images.append(True)
    else:
        MST_images.append(False)

print("images", images.shape)
MST_images = np.array(MST_images)
print("len MST_images", len(MST_images))
assert len(MST_images[MST_images==True]) == 124
print("MST_images==True", len(MST_images[MST_images==True]))


def get_image_pairs(sub, session, func_task_name, designdir):
    """Loads design files and processes image pairs for a given session."""
    _, _, _, _, image_names, unique_images, _ = utils_mindeye.load_design_files(
        sub=sub,
        session=session,
        func_task_name=func_task_name,
        designdir=designdir,
        design_ses_list=[session]  # Ensure it's a list
    )
    return utils_mindeye.process_images(image_names, unique_images)

all_dicts = []
for s_idx, s in enumerate(ses_list):
    im, vo, _ = get_image_pairs(sub, s, func_task_name, designdir)
    assert len(im) == len(vo)
    all_dicts.append({k:v for k,v in enumerate(vo)})

assert session == 'ses-03'
image_to_indices = defaultdict(lambda: [[] for _ in range(len(ses_list))])
for ses_idx, idx_to_name in enumerate(all_dicts):
    for idx, name in idx_to_name.items():
        image_to_indices[name][ses_idx].append(idx)
        
image_to_indices = dict(image_to_indices)

utils_mindeye.seed_everything(0)
MST_idx = np.array([v for k,v in image_to_indices.items() if 'MST_pairs' in k])
# train_image_indices = np.array([]).astype(np.int8)
# test_image_indices = np.concatenate([np.where(MST_images == True)[0], np.where(MST_images == False)[0]])
train_image_indices = np.where(MST_images == False)[0]
test_image_indices = np.where(MST_images == True)[0]
print(len(train_image_indices), len(test_image_indices))

# for now, use the first subset of repeats only
MST_idx = MST_idx[:,0,0]
print("MST_idx", MST_idx.shape)

projectDir = os.path.dirname(os.path.realpath(__file__)) #'.../rt-cloud/projects/project_name'
today = date.today()
dateString = today.strftime('%Y%m%d')
today = date.today()
# Month abbreviation, day and year	
d4 = today.strftime("%b-%d-%Y")
# Initialize the remote procedure call (RPC) for the data_analyser
# (aka projectInferface). This will give us a dataInterface for retrieving
# files, a subjectInterface for giving feedback, a webInterface
# for updating what is displayed on the experimenter's webpage,
# and enable BIDS functionality
clientInterfaces = ClientInterface(rpyc_timeout=999999)
webInterface  = clientInterfaces.webInterface
bidsInterface = clientInterfaces.bidsInterface
subjInterface = clientInterfaces.subjInterface
subjInterface.subjectRemote = True

"""====================REAL-TIME ANALYSIS BELOW====================
===================================================================="""
# clear existing web browser plots if there are any
try:
    webInterface.clearAllPlots()
except:
    pass

# get the mask and the reference files
ndscore_events = [pd.read_csv(f'{data_path}/events/sub-005_ses-03_task-C_run-{run+1:02d}_events.tsv', sep = "\t", header = 0) for run in range(n_runs)]  # create a new list of events_df's which will have the trial_type modified to be unique identifiers
ndscore_tr_labels = [pd.read_csv(f"{data_path}/events/sub-005_ses-03_task-C_run-{run+1:02d}_tr_labels.csv") for run in range(n_runs)]
tr_length = 1.5
mask_img = nib.load(f'{data_path}/sub-005_final_mask.nii.gz')  # nsdgeneral mask in functional space
ses1_boldref= f"{data_path}/sub-005_ses-01_task-C_run-01_space-T1w_boldref.nii.gz"  # preprocessed boldref from ses-01
ses3_vol0 = f"{derivatives_path}/vols/sub-005_ses-03_task-C_run-01_bold_0000.nii.gz" # first volume (vol0000) of real-time session
# day2_to_day1_mat =  f"{storage_path}/day2ref_to_day1ref"
def fast_apply_mask(target=None,mask=None):
    return target[np.where(mask == 1)].T
ses1_boldref_nib = nib.load(ses1_boldref)
union_mask = np.load(f"{data_path}/union_mask_from_ses-01-02.npy")
# apply union mask to the nsdgeneral ROI and convert to nifti
assert mask_img.get_fdata().sum() == union_mask.shape
union_mask_img = new_img_like(mask_img, union_mask)

# apply union_mask to mask_img and return nifti object

# Get the data as a boolean array
mask_data = mask_img.get_fdata().astype(bool)

# Flatten only the True voxels in the mask
true_voxel_indices = np.where(mask_data.ravel())[0]

# Apply the union_mask (boolean mask of size 19174)
selected_voxel_indices = true_voxel_indices[union_mask]

# Create a new flattened mask with all False
new_mask_flat = np.zeros(mask_data.size, dtype=bool)

# Set selected voxels to True
new_mask_flat[selected_voxel_indices] = True

# Reshape back to original 3D shape
new_mask_data = new_mask_flat.reshape(mask_data.shape)

# Create new NIfTI image
union_mask_img = nib.Nifti1Image(new_mask_data.astype(np.uint8), affine=mask_img.affine)

print("union_mask_img.shape", union_mask_img.shape)
print("union mask num voxels", int(union_mask_img.get_fdata().sum()))

lss_glm = FirstLevelModel(t_r=tr_length,slice_time_ref=0,hrf_model='glover',
                        drift_model='polynomial',high_pass=None,mask_img=mask_img,
                        signal_scaling=False,smoothing_fwhm=None,noise_model='ar1',
                        n_jobs=-1,verbose=-1,memory_level=1,minimize_memory=True)

def do_reconstructions(betas_tt):
    """
    takes in the beta map for a stimulus trial in torch tensor format (tt)

    returns reconstructions and clipvoxels for retrievals
    """
    # start_reconstruction_time = time.time()
    model.to(device)
    model.eval().requires_grad_(False)
    clipvoxelsTR = None
    reconsTR = None
    num_samples_per_image = 1
    with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
        voxel = betas_tt
        voxel = voxel.to(device)
        voxel_ridge = model.ridge(voxel[:,[0]],0) # 0th index of subj_list
        backbone0, clip_voxels0, blurry_image_enc0 = model.backbone(voxel_ridge)
        clip_voxels = clip_voxels0
        backbone = backbone0
        blurry_image_enc = blurry_image_enc0[0]
        clipvoxelsTR = clip_voxels.cpu()
        prior_out = model.diffusion_prior.p_sample_loop(backbone.shape, 
                        text_cond = dict(text_embed = backbone), 
                        cond_scale = 1., timesteps = 20)  
        for i in range(len(voxel)):
            samples = utils_mindeye.unclip_recon(prior_out[[i]],
                            diffusion_engine,
                            vector_suffix,
                            num_samples=num_samples_per_image)
            if reconsTR is None:
                reconsTR = samples.cpu()
            else:
                reconsTR = torch.vstack((reconsTR, samples.cpu()))
            imsize = 224
            reconsTR = transforms.Resize((imsize,imsize), antialias=True)(reconsTR).float().numpy().tolist()

        return reconsTR, clipvoxelsTR
    
def batchwise_cosine_similarity(Z,B):
    Z = Z.flatten(1)
    B = B.flatten(1).T
    Z_norm = torch.linalg.norm(Z, dim=1, keepdim=True)  # Size (n, 1).
    B_norm = torch.linalg.norm(B, dim=0, keepdim=True)  # Size (1, b).
    cosine_similarity = ((Z @ B) / (Z_norm @ B_norm)).T
    return cosine_similarity

def get_top_retrievals(clipvoxel, all_images, total_retrievals=1):
    '''
    clipvoxel: output from do_recons that contains that information needed for retrievals
    all_images: all ground truth actually seen images by the participant in day 2 run 1

    outputs the top retrievals
    '''
    values_dict = {}
    with torch.amp.autocast('cuda', dtype=torch.float16):
        emb = clip_img_embedder(torch.reshape(all_images,(all_images.shape[0], 3, 224, 224)).to(device)).float() # CLIP-Image
        emb = emb.cpu()
        emb_ = clipvoxel # CLIP-Brain
        emb = emb.reshape(len(emb),-1)
        emb_ = np.reshape(emb_, (1, 425984))
        emb = nn.functional.normalize(emb,dim=-1)
        emb_ = nn.functional.normalize(emb_,dim=-1)
        emb_ = emb_.float()
        fwd_sim = batchwise_cosine_similarity(emb_,emb)  # brain, clip
        print("Given Brain embedding, find correct Image embedding")
    fwd_sim = np.array(fwd_sim.cpu())
    which = np.flip(np.argsort(fwd_sim, axis = 0))
    
    imsize = 224
    for attempt in range(total_retrievals):
        values_dict[f"attempt{(attempt+1)}"] = transforms.Resize((imsize,imsize), antialias=True)(all_images[which[attempt].copy()]).float().numpy().tolist()
    return values_dict

def convert_image_array_to_PIL(image_array):
    if image_array.ndim == 4:
        image_array = image_array[0]

    # get the dimension to h, w, 3|1
    if image_array.ndim == 3 and image_array.shape[0] == 3:
        image_array = np.transpose(image_array, (1, 2, 0))  # Change shape to (height, width, 3)
    
    # clip the image array to 0-1
    image_array = np.clip(image_array, 0, 1)
    # convert the image array to uint8
    image_array = (image_array * 255).astype('uint8')
    # convert the image array to PIL
    return Image.fromarray(image_array)


# go through each run
for run_num in range(1,2):
    print(f"==START OF DAY 2 RUN {run_num}!==\n")
    # stream in that data!
    # import debugpy
    # os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"
    # debugpy.listen(("0.0.0.0", 5678))  # listen on all interfaces, port 5678
    # print("Waiting for debugger to attach...")
    # debugpy.wait_for_client()
    # debugpy.breakpoint()
    # print("Debugger attached, continuing...")
    
    # breakpoint()
    data_stream = BidsInterface()
    cwd = os.getcwd()
    print("cwd ", cwd)
    print(os.listdir(f"{data_path}/raw_bids"))
    streamID = data_stream.initBidsStream(f"{data_path}/raw_bids", **{'datatype': 'func',
                                        'extension': '.nii.gz',
                                        'run': "01",
                                        'session': '03',
                                        'subject': '005',
                                        'suffix': 'bold',
                                        'task': 'C'})

    print(f"Run {run_num} started")
    mc_params = []
    imgs = []
    events_df = ndscore_events[run_num - 1]
    tr_labels_hrf = ndscore_tr_labels[run_num - 1]["tr_label_hrf"].tolist()
    beta_maps_list = []
    all_trial_names_list = []
    # get the all images tensor
    all_images = None
    seen_label_before = ["blank"]
    # get the list of all images in torch tensor format for this run (should be 62 or 63 images)
    all_COCO_ids = []
    for TR in range(186):
        if tr_labels_hrf[TR] not in seen_label_before:
            seen_label_before.append(tr_labels_hrf[TR])
            image_COCO_id = int(float(tr_labels_hrf[TR].split("_")[1])) - 1
            new_image_pt = torch.from_numpy(np.reshape(images[image_COCO_id],(1,3,224,224)))
            all_images = new_image_pt if all_images == None else torch.vstack((all_images, new_image_pt))
            all_COCO_ids.append(image_COCO_id)
    print(all_COCO_ids)
    stimulus_trial_counter = 0
    for TR in range(186):
        print(f"TR {TR}")
        # stream in the nifti
        incremental_bids_image = data_stream.getIncremental(streamID,volIdx=TR,
                                        timeout=999999,demoStep=1.6)
        image_data = incremental_bids_image.image
        current_label = tr_labels_hrf[TR]

        
        if TR == 0:
            day2_run1_bold_ref = image_data
            # make the day 2 bold ref
            nib.save(image_data, day2_boldref)
            # save the transformation from the day 2 bold ref to the day 1 
            os.system(f"flirt -in {day2_boldref} \
            -ref {day1_boldref} \
            -omat {day2_to_day1_mat} \
            -dof 6")
        # load nifti file
        tmp = f'{data_and_model_storage_path}/day2_subj1/tmp_run{run_num}.nii.gz'
        nib.save(index_img(image_data,0),tmp)
        start = time.time()
        # on first tr the motion correction will have no issue so that mc_params is properly populated
        mc = f'{data_and_model_storage_path}/day2_subj1/tmp_mc_run{run_num}'
        os.system(f"mcflirt -in {tmp} -reffile {day2_boldref} -out {mc} -plots -mats")
        mc_params.append(np.loadtxt(f'{mc}.par'))
        mc_day1_aligned = f'{data_and_model_storage_path}/day2_subj1/tmp_mc_day1_aligned_run{run_num}'
        current_tr_to_day1 = f"{data_and_model_storage_path}/day2_subj1/current_tr_to_day1_run{run_num}"
        os.system(f"convert_xfm -concat {day2_to_day1_mat} -omat {current_tr_to_day1} {mc}.mat/MAT_0000")    
        # apply concatenated matrix to the current TR
        os.system(f"flirt -in {tmp} \
        -ref {day1_boldref} \
        -out {mc_day1_aligned} \
        -init {current_tr_to_day1} \
        -applyxfm")
        # now delete the mc from current tr to bold reference mat
        os.system(f"rm -r {mc}.mat") 
        imgs.append(get_data(mc_day1_aligned + ".nii.gz")) # only add to imgs list
        if tr_labels_hrf[TR] != tr_labels_hrf[TR + 1] and tr_labels_hrf[TR] != "blank":
            # the current image is the last TR of a real image
            cropped_events = events_df[events_df.trial_number <= int(float(tr_labels_hrf[TR].split("_")[3]))]
            for i_trial, trial in cropped_events.iterrows():
                cropped_events.loc[i_trial, "trial_type"] = "reference" if i_trial < (len(cropped_events) - 1) else "probe"
            # get the image id from this stimulus trial that we are fitting a model on
            image_COCO_id = int(float(tr_labels_hrf[TR].split("_")[1])) - 1
            # collect all of the images at each TR into a 4D time series
            img = np.rollaxis(np.array(imgs),0,4)
            img = new_img_like(day1_boldref_nibd,img,copy_header=True)
            # run the model with mc_params confounds to motion correct
            lss_glm.fit(run_imgs=img,events=cropped_events, confounds = pd.DataFrame(np.array(mc_params)))
            # get the beta map and mask it
            beta_map = lss_glm.compute_contrast("probe", output_type="effect_size")
            beta_map_np = beta_map.get_fdata()
            beta_map_np = fast_apply_mask(target=beta_map_np,mask=mask_img.get_fdata())
            beta_maps_list.append(beta_map_np)
            index_for_norm = min(20, stimulus_trial_counter + 1)
            beta_map_np = (beta_map_np - np.mean(np.vstack(beta_maps_list)[:index_for_norm,:], axis = 0)) / np.std(np.vstack(beta_maps_list)[:index_for_norm,:], axis = 0)
            beta_map_np = np.reshape(beta_map_np, (1,1,25225))
            betas_tt = torch.Tensor(beta_map_np).to("cpu")
            new_image_pt = torch.from_numpy(images[image_COCO_id])
            reconsTR, clipvoxelsTR = do_reconstructions(betas_tt)
            values_dict = get_top_retrievals(clipvoxelsTR, all_images=all_images, stimulus_trial_counter = stimulus_trial_counter)
            values_dict["recons"] = reconsTR
            # subjInterface.setResultDict allows us to send to the analysis listener immediately
            subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                                        values=values_dict)
            stimulus_trial_counter += 1
        else:
            if tr_labels_hrf[TR] != "blank":
                # this is the non-last TR of a real image
                values_dict = {}
                image_COCO_id = int(float(tr_labels_hrf[TR].split("_")[1])) - 1
                imsize = 50
                values_dict["ground_truth"] = transforms.Resize((imsize,imsize))(all_images[stimulus_trial_counter]).float().numpy().tolist()
                subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                                            values=values_dict)
            else:
                # blank TR
                # when we are not at the end of a stimulus trial, send an empty dictionary to the analysis listener with "pass"
                subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                                values={'pass': "pass"})
        
    print(f"==END OF RUN {run_num}!==\n")
    bidsInterface.closeStream(streamID)

