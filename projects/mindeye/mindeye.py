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
import zlib
import base64
from copy import deepcopy

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
    output_path = config['output_path']
    fsl_path = config['fsl_path']
    assert os.path.exists(storage_path), "The specified data and model storage path does not exist."
    assert os.path.exists(data_path), "The specified BOLD path does not exist."
    assert os.path.exists(derivatives_path), "The specified derivatives path does not exist."
    assert os.path.exists(output_path), "The specified output path does not exist."
    assert os.path.exists(fsl_path), "The specified FSL path does not exist."
except FileNotFoundError:
    raise FileNotFoundError("config.json file not found. Please create it with the required paths.")

imsize = 224

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
model_name = "sub-005_ses-01-03_task-C_bs24_MST_rishab_MSTsplit_unionmask_ses-01-03_finetune"
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
tag=f'{model_name}.pth'
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
session = "ses-06"
task = 'C'  # 'study' or 'A'; used to search for functional run in bids format
func_task_name = 'C'  # 'study' or 'A'; used to search for functional run in bids format
n_runs = 7

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
if sub == 'sub-005' and session == 'ses-06':
    pass
    # assert len(all_MST_images) == 630
else:
    assert len(all_MST_images) == 693

resize_transform = transforms.Resize((imsize, imsize))
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
if sub == 'sub-005' and session == 'ses-06':
    pass
else:
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

image_to_indices = defaultdict(lambda: [[] for _ in range(len(ses_list))])
for ses_idx, idx_to_name in enumerate(all_dicts):
    for idx, name in idx_to_name.items():
        image_to_indices[name][ses_idx].append(idx)
        
image_to_indices = dict(image_to_indices)

utils_mindeye.seed_everything(0)
# Collect indices for images containing 'MST_pairs'
MST_idx = [v[0][0] if len(v[0]) > 0 else None for k, v in image_to_indices.items() if 'MST_pairs' in k]

# Remove any None values (in case some images don't have repeats)
MST_idx = [idx for idx in MST_idx if idx is not None]

print("MST_idx", len(MST_idx))

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
tmpPath = f"{data_path}/tmp/"  # temporary path to save nifti file at each TR
os.makedirs(tmpPath, exist_ok=True)
ndscore_events = [pd.read_csv(f'{data_path}/events/{sub}_{session}_task-{func_task_name}_run-{run+1:02d}_events.tsv', sep = "\t", header = 0) for run in range(n_runs)]  # create a new list of events_df's which will have the trial_type modified to be unique identifiers
ndscore_tr_labels = [pd.read_csv(f"{data_path}/events/{sub}_{session}_task-{func_task_name}_run-{run+1:02d}_tr_labels.csv") for run in range(n_runs)]
tr_length = 1.5
mask_img = nib.load(f'{data_path}/sub-005_final_mask.nii.gz')  # nsdgeneral mask in functional space
fmriprep_boldref = f"{data_path}/sub-005_ses-01_task-C_run-01_space-T1w_boldref.nii.gz"  # preprocessed boldref from ses-01
rt_vol0 = f"{tmpPath}/vol0.nii.gz" # first volume (vol0000) of real-time session

def fast_apply_mask(target=None,mask=None):
    return target[np.where(mask == 1)].T

fmriprep_boldref_nib = nib.load(fmriprep_boldref)
union_mask = np.load(f"{data_path}/union_mask_from_ses-01-02.npy")

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

def compress_and_encode_image(image_array):
    # Convert the image array to bytes, compress, and encode
    if image_array.dtype != np.uint8:
        image_array = image_array.astype(np.uint8)
    compressed_data = zlib.compress(image_array.tobytes())
    encoded_data = base64.b64encode(compressed_data).decode('utf-8')
    return encoded_data


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

            reconsTR = transforms.Resize((imsize, imsize), antialias=True)(reconsTR)

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
        emb = clip_img_embedder(torch.reshape(all_images,(all_images.shape[0], 3, imsize, imsize)).to(device)).float() # CLIP-Image
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
    
    for attempt in range(total_retrievals):
        image_tensor = all_images[which[attempt].copy()]  # [C, H, W]
        if image_tensor.dim() == 4 and image_tensor.shape[0] == 1:
            image_tensor = image_tensor.squeeze(0)  # Remove extra batch dim
        resized = transforms.Resize((imsize, imsize), antialias=True)(image_tensor.unsqueeze(0))  # [1, C, H, W]
        # squeeze(0) goes from [1, 3, H, W] -> [3, H, W]
        # permute(1, 2, 0) undoes the permute(2, 0, 1) from loading in the image
        # clamp(0, 1) makes sure the values are all between 0 and 1 (prevents under/overflow due to floating point imprecision)
        # * 255 converts from [0, 1] (floating point) to [0, 255] (8-bit)
        # byte() casts to uint8
        # numpy() casts from torch tensor to numpy array
        # print(f"resized shape before squeeze: {resized.shape}")
        image_array = (resized.squeeze(0).permute(1, 2, 0).clamp(0, 1) * 255).byte().numpy()
        encoded_image = compress_and_encode_image(image_array)
        values_dict[f"attempt{(attempt+1)}"] = encoded_image

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

plot_images=False
save_individual_images=False
save_all_recons=False
evaluate_session=False

mc_dir = f"{derivatives_path}/motion_corrected"
mc_resampled_dir = f"{derivatives_path}/motion_corrected_resampled"
if os.path.exists(mc_dir):
    shutil.rmtree(mc_dir)
os.makedirs(mc_dir)
if os.path.exists(mc_resampled_dir):
    shutil.rmtree(mc_resampled_dir)
os.makedirs(mc_resampled_dir)

rt_to_fmriprep_mat = f'{derivatives_path}/rtref_to_ses1ref'
os.environ['FSLOUTPUTTYPE'] = 'NIFTI_GZ'
assert np.all(fmriprep_boldref_nib.affine == union_mask_img.affine)
all_betas = []
shown_filenames = dict()

# Loop over all 11 runs in the session
n_runs = 11

# go through each run
for run_num in range(1, n_runs + 1):
    print(f"==START OF DAY 2 RUN {run_num}!==\n")
    cwd = os.getcwd()
    print("cwd ", cwd)
    # print(os.listdir(f"{data_path}/raw_bids"))
    run_to_dicom = {1:5, 2:6, 3:7, 4:8, 5:10, 6:11, 7:12, 8:13, 9:15, 10:16, 11:17}
    
    # dicomNamePattern = "{RUN}-{TR}-1.dcm"  # use this for scanner dicoms WITHOUT "RT Start On"
    dicomNamePattern = "001_{RUN:06d}_{TR:06d}.dcm"  # use this for scanner dicoms WITH "RT Start On"
    
    dicomScanNamePattern = stringPartialFormat(dicomNamePattern, 'RUN', run_to_dicom[run_num])

    dicom_filename = "005_ses06_rtmindeye"  # when registering the subject into the scanner, this is what was entered for last name and subject ID
    dicomDir = f"/home/scontrol/20250729.{dicom_filename}.{dicom_filename}"  # directory to use when the scanner mounts to the real-time computer
    # dicomDir = f"{data_path}/dicom_ses-03"
    streamID = bidsInterface.initDicomBidsStream(dicomDir, dicomScanNamePattern,
                                               300000, anonymize=False,
                                               **{'subject':f'{dicom_filename}',
                                                  'run':f'{run_num}',
                                                  'task':'C'})

    print(f"Run {run_num} started")
    mc_params = []
    imgs = []
    events_df = ndscore_events[run_num - 1]
    tr_labels_hrf = ndscore_tr_labels[run_num - 1]["tr_label_hrf"].tolist()
    events_df = events_df[events_df['image_name'] != 'blank.jpg']  # must drop blank.jpg after tr_labels_hrf is defined to keep indexing consistent
    beta_maps_list = []
    all_trial_names_list = []
    all_images = None

    save_path = f"{output_path}/{sub}_{session}_task-{func_task_name}_run-{run_num:02d}_recons"
    os.makedirs(save_path, exist_ok=True)
    if save_individual_images:
        os.makedirs(os.path.join(save_path, "individual_images"), exist_ok=True)

    all_recons_save = []
    all_clipvoxels_save = []
    all_ground_truth_save = []
    all_retrieved_save = []

    stimulus_trial_counter = 0
    # Counter for MST_pairs trials and evenly spaced recon points
    mst_trial_counter = 0
    mst_total = 63  # total MST_pairs trials in a run (adjust if needed)
    mst_recon_points = np.linspace(5, mst_total, 7, dtype=int).tolist()
    T1_brain = f"{data_path}/{sub}_desc-preproc_T1w_brain.nii.gz"
    n_trs = 192
    assert len(tr_labels_hrf) == n_trs, "there should be image labels for each TR"
    assert all(label in image_names for label in tr_labels_hrf if label != 'blank'), "Some labels in tr_labels_hrf are missing from image_names."
    assert len(images) > n_trs, "images array is too short."

    for TR in range(n_trs-1):
        print(f"TR {TR}")
        incremental_bids_image = bidsInterface.getIncremental(streamID,volIdx=TR+1,
                                        timeout=999999,demoStep=0)
        image_data = incremental_bids_image.image
        curr_nifti = f'{tmpPath}/temp.nii'
        nib.save(image_data, curr_nifti)

        current_label = tr_labels_hrf[TR]
        print(current_label)
        
        if TR == 0 and run_num == 1:
            nib.save(image_data, rt_vol0)  # real-time volume 0, will be used to motion correct all future volumes

            os.system(f"flirt -in {rt_vol0} \
                -ref {fmriprep_boldref} \
                -omat {rt_to_fmriprep_mat} \
                -dof 6")  # register real-time volume 0 to the fmriprep bold reference image and output the corresponding transformation matrix

        mc = f"{tmpPath}/temp_aligned"
        os.system(f"{fsl_path}/mcflirt -in {curr_nifti} -reffile {rt_vol0} -out {mc} -plots -mats")
        mc_params.append(np.loadtxt(f'{mc}.par'))

        current_tr_to_orig_ses = f"{derivatives_path}/current_tr_to_orig_ses_run{run_num}"
        os.system(f"convert_xfm -concat {rt_to_fmriprep_mat} -omat {current_tr_to_orig_ses} {mc}.mat/MAT_0000")  # combine 2 transforms: motion correction and cross-session registration
        
        final_vol = f"{mc_resampled_dir}/{sub}_{session}_run-{run_num:02d}_{TR:04d}_mc_boldres.nii.gz"
        os.system(f"flirt -in {curr_nifti} \
            -ref {fmriprep_boldref} \
            -out {final_vol} \
            -init {current_tr_to_orig_ses} \
            -applyxfm")  # apply combined transformation matrix to the current TR

        os.system(f"rm -r {mc}.mat")
        imgs.append(get_data(final_vol))

        if current_label not in ('blank', 'blank.jpg'):
            events_df = events_df.copy()
            events_df['onset'] = events_df['onset'].astype(float)

            run_start_time = events_df['onset'].iloc[0]
            events_df = events_df.copy()
            events_df['onset'] -= run_start_time

            cropped_events = events_df[events_df.onset <= TR*tr_length]
            cropped_events = cropped_events.copy()
            cropped_events.loc[:, 'trial_type'] = np.where(cropped_events['trial_number'] == stimulus_trial_counter, "probe", "reference")
            cropped_events = cropped_events.drop(columns=['is_correct', 'image_name', 'response_time', 'trial_number'])

            # collect all of the images at each TR into a 4D time series
            img = np.rollaxis(np.array(imgs),0,4)
            img = new_img_like(fmriprep_boldref_nib,img,copy_header=True)
            # run the model with mc_params confounds to motion correct
            lss_glm = FirstLevelModel(t_r=tr_length,slice_time_ref=0,hrf_model='glover',
                        drift_model='cosine', drift_order=1,high_pass=0.01,mask_img=union_mask_img,
                        signal_scaling=False,smoothing_fwhm=None,noise_model='ar1',
                        n_jobs=-1,verbose=-1,memory_level=1,minimize_memory=True)
            
            lss_glm.fit(run_imgs=img, events=cropped_events, confounds = pd.DataFrame(np.array(mc_params)))
            dm = lss_glm.design_matrices_[0]
            # get the beta map and mask it
            beta_map = lss_glm.compute_contrast("probe", output_type="effect_size")
            beta_map_np = beta_map.get_fdata()
            beta_map_np = fast_apply_mask(target=beta_map_np,mask=union_mask_img.get_fdata())
            all_betas.append(beta_map_np)
            
            if current_label not in shown_filenames.keys():
                shown_filenames[current_label] = [len(all_betas)]
                is_repeat = False
            else:
                shown_filenames[current_label].append(len(all_betas))
                is_repeat = True
                print(f"The following image is a repeat!\n{shown_filenames[current_label]}")

            if "MST_pairs" in current_label and run_num >= 2:
                mst_trial_counter += 1
                if mst_trial_counter in mst_recon_points:
                    correct_image_index = np.where(current_label == vox_image_names)[0][0]  # using the first occurrence based on image name, assumes that repeated images are identical (which they should be)
                    z_mean = np.mean(np.array(all_betas), axis=0)
                    z_std = np.std(np.array(all_betas), axis=0)
                    if is_repeat:
                        beta_repeat_idxs = shown_filenames[current_label]
                        assert len(beta_repeat_idxs) > 1  # this image has been shown more than once
                        betas_repeats = []
                        for b in beta_repeat_idxs:
                            print(f"Averaging over {len(beta_repeat_idxs)} repeats")
                            # re-z-score the older betas in addition to the newest beta since we have more data to z-score with
                            tmp = ((np.array(all_betas) - z_mean) / (z_std + 1e-6))[b-1]
                            betas_repeats.append(tmp)
                        betas = np.mean(np.array(betas_repeats), axis=0)  # average beta patterns over all available repeats
                    else:
                        betas = ((np.array(all_betas) - z_mean) / (z_std + 1e-6))[-1]  # use only the beta pattern from the most recent image
                    betas = betas[np.newaxis, np.newaxis, :]
                    betas_tt = torch.Tensor(betas).to("cpu")
                    reconsTR, clipvoxelsTR = do_reconstructions(betas_tt)
                    if clipvoxelsTR is None:
                        with torch.no_grad(), torch.cuda.amp.autocast(dtype=torch.float16):
                            voxel = betas_tt
                            voxel = voxel.to(device)
                            assert voxel.shape[1] == 1
                            voxel_ridge = model.ridge(voxel[:,[-1]],0) # 0th index of subj_list
                            backbone0, clip_voxels0, blurry_image_enc0 = model.backbone(voxel_ridge)
                            clip_voxels = clip_voxels0
                            backbone = backbone0
                            blurry_image_enc = blurry_image_enc0[0]
                            clipvoxelsTR = clip_voxels.cpu()

                    values_dict = get_top_retrievals(clipvoxelsTR, all_images=images[MST_idx], total_retrievals=5)
                    values_dict["recons"] = compress_and_encode_image((reconsTR.squeeze(0).permute(1, 2, 0).clamp(0, 1) * 255).byte().numpy())
                    reconsTR = reconsTR.half().numpy()

                    resized = transforms.Resize((imsize, imsize), antialias=True)(images[correct_image_index])
                    image_array = (resized.squeeze(0).permute(1, 2, 0).clamp(0, 1) * 255).byte().numpy()
                    encoded_image = compress_and_encode_image(image_array)
                    values_dict["ground_truth"] = encoded_image

                    # subjInterface.setResultDict allows us to send to the analysis listener immediately
                    subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                                                values=values_dict)

                    image_array = reconsTR[0]
                    # If the image has 3 channels (RGB), you need to reorder the dimensions
                    if image_array.ndim == 3 and image_array.shape[0] == 3:
                        image_array = np.transpose(image_array, (1, 2, 0))  # Change shape to (height, width, 3)

                    # Display the image
                    if plot_images:
                        # plot original and reconstructed images
                        plt.figure(figsize=(10, 5))
                        plt.subplot(1, 2, 1)
                        plt.title("Original Image")
                        plt.imshow(images[correct_image_index].half().numpy().transpose(1, 2, 0), cmap='gray')
                        plt.axis('off')
                        plt.subplot(1, 2, 2)
                        plt.title("Reconstructed Image")
                        plt.imshow(image_array, cmap='gray' if image_array.ndim == 2 else None)
                        plt.axis('off')
                        plt.show()

                        # plot original with top 5 retrievals
                        plt.figure(figsize=(10, 5))
                        plt.subplot(1, 6, 1)
                        plt.title("Original Image")
                        plt.imshow(images[correct_image_index].half().numpy().transpose(1, 2, 0), cmap='gray')
                        plt.axis('off')
                        for i in range(5):
                            plt.subplot(1, 6, i+2)
                            plt.title(f"Retrieval {i+1}")
                            plt.imshow(np.array(values_dict[f"attempt{i+1}"][0]).transpose(1, 2, 0), cmap='gray')
                            plt.axis('off')
                        plt.show()

                    # save reconstructed image, retrieved images, clip_voxels, and ground truth image
                    if save_individual_images:
                        # save the reconstructed image
                        convert_image_array_to_PIL(image_array).save(os.path.join(save_path, "individual_images", f"run{run_num}_TR{TR}_reconstructed.png"))
                        # save the retrieved images
                        for key, value in values_dict.items():
                            if key not in ('ground_truth', 'recons'):
                                convert_image_array_to_PIL(np.array(value)).save(os.path.join(save_path, "individual_images", f"run{run_num}_TR{TR}_retrieved_{key}.png"))
                        # save the clip_voxels
                        np.save(os.path.join(save_path, "individual_images", f"run{run_num}_TR{TR}_clip_voxels.npy"), clipvoxelsTR)
                        # save the ground truth image
                        convert_image_array_to_PIL(images[correct_image_index].half().numpy()).save(os.path.join(save_path, "individual_images", f"run{run_num}_TR{TR}_ground_truth.png"))
                    all_recons_save.append(image_array)
                    all_clipvoxels_save.append(clipvoxelsTR)
                    all_ground_truth_save.append(images[correct_image_index].half().numpy())
                    all_retrieved_save.append([np.array(value) for key, value in values_dict.items() if (not ('ground_truth' in key))])
                else:
                    subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                        values={'pass': "pass"})

            else:
                subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                    values={'pass': "pass"})
            
            stimulus_trial_counter += 1
        elif current_label == 'blank.jpg':
            subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                values={'pass': "pass"})
            stimulus_trial_counter += 1
        else:
            assert current_label == 'blank'
            # blank TR
            # when we are not at the end of a stimulus trial, send an empty dictionary to the analysis listener with "pass"
            subjInterface.setResultDict(name=f'run{run_num}_TR{TR}',
                            values={'pass': "pass"})
        
    print(f"==END OF RUN {run_num}!==\n")

    # save the design matrix for the current run
    dm.to_csv(os.path.join(save_path, f"design_run-{run_num:02d}.csv"))
    plot_design_matrix(dm, output_file=os.path.join(save_path, "dm"))
    dm[['probe', 'reference']].plot(title='Probe/Reference Regressors', figsize=(10, 4))
    plt.savefig(os.path.join(save_path, "regressors"))
    # save betas so far
    np.save(os.path.join(save_path, f"betas_run-{run_num:02d}.npy"), np.array(all_betas))
    print(f"==END OF RUN {run_num}!==\n")
    # save the tensors
    if save_all_recons:
        all_recons_save_tensor = torch.tensor(all_recons_save).permute(0,3,1,2)
        all_clipvoxels_save_tensor = torch.stack(all_clipvoxels_save, dim=0)
        all_ground_truth_save_tensor = torch.tensor(all_ground_truth_save)
        all_retrieved_save_tensor = torch.stack([torch.tensor(np.array(item)) for item in all_retrieved_save], dim=0)
        torch.save(all_recons_save_tensor, os.path.join(save_path, "all_recons.pt"))
        torch.save(all_clipvoxels_save_tensor, os.path.join(save_path, "all_clipvoxels.pt"))
        torch.save(all_ground_truth_save_tensor, os.path.join(save_path, "all_ground_truth.pt"))
        torch.save(all_retrieved_save_tensor, os.path.join(save_path, "all_retrieved.pt"))
        print("all_recons_save_tensor.shape: ", all_recons_save_tensor.shape)
        print("all_clipvoxels_save_tensor.shape: ", all_clipvoxels_save_tensor.shape)
        print("all_ground_truth_save_tensor.shape: ", all_ground_truth_save_tensor.shape)
        print("all_retrieved_save_tensor.shape: ", all_retrieved_save_tensor.shape)
        print("All tensors saved successfully on ", save_path)
    
    bidsInterface.closeStream(streamID)


print('all done!')
if evaluate_session:
    # Run evaluation metrics
    from utils_mindeye import calculate_retrieval_metrics, calculate_alexnet, calculate_clip, calculate_swav, calculate_efficientnet_b1, calculate_inception_v3, calculate_pixcorr, calculate_ssim, deduplicate_tensors
    all_recons_save_tensor = []
    all_clipvoxels_save_tensor = []
    all_ground_truth_save_tensor = []
    all_retrieved_save_tensor = []

    for run_num in range(n_runs):
        save_path = f"{output_path}/sub-005_ses-03_task-C_run-{run_num+1:02d}_recons"

        try:
            # recons = torch.load(os.path.join(save_path, "all_recons.pt")).to(torch.float16)
            # clipvoxels = torch.load(os.path.join(save_path, "all_clipvoxels.pt")).to(torch.float16)
            # ground_truth = torch.load(os.path.join(save_path, "all_ground_truth.pt")).to(torch.float16)
            recons = torch.load(os.path.join(save_path, "all_recons.pt")).to(torch.float16).to(device)
            clipvoxels = torch.load(os.path.join(save_path, "all_clipvoxels.pt")).to(torch.float16).to(device)
            ground_truth = torch.load(os.path.join(save_path, "all_ground_truth.pt")).to(torch.float16).to(device)

            all_recons_save_tensor.append(recons)
            all_clipvoxels_save_tensor.append(clipvoxels)
            all_ground_truth_save_tensor.append(ground_truth)
        except FileNotFoundError:
            print("Error: Tensors not found. Please check the save path.")

    # Concatenate tensors along the first dimension
    try:
        all_recons_save_tensor = torch.cat(all_recons_save_tensor, dim=0)
        all_clipvoxels_save_tensor = torch.cat(all_clipvoxels_save_tensor, dim=0)
        all_ground_truth_save_tensor = torch.cat(all_ground_truth_save_tensor, dim=0)
    except RuntimeError:
        print('Error: Couldn\'t concatenate tensors')

    with torch.autocast(device_type="cuda", dtype=torch.float16):
        unique_clip_voxels, unique_ground_truth, duplicated = deduplicate_tensors(all_clipvoxels_save_tensor, all_ground_truth_save_tensor)
        
        print('calculating retrieval subset 0 (first set of repeats)')
        unique_clip_voxels_subset0 = all_clipvoxels_save_tensor[np.array(duplicated)[:,0]]
        unique_ground_truth_subset0 = all_ground_truth_save_tensor[np.array(duplicated)[:,0]]
        all_fwd_acc_subset0, all_bwd_acc_subset0 = calculate_retrieval_metrics(unique_clip_voxels_subset0, unique_ground_truth_subset0)

        print('calculating retrieval subset 1 (second set of repeats)')
        unique_clip_voxels_subset1 = all_clipvoxels_save_tensor[np.array(duplicated)[:,1]]
        unique_ground_truth_subset1 = all_ground_truth_save_tensor[np.array(duplicated)[:,1]]
        all_fwd_acc_subset1, all_bwd_acc_subset1 = calculate_retrieval_metrics(unique_clip_voxels_subset1, unique_ground_truth_subset1)
        pixcorr = calculate_pixcorr(all_recons_save_tensor, all_ground_truth_save_tensor)
        ssim_ = calculate_ssim(all_recons_save_tensor, all_ground_truth_save_tensor)
        alexnet2, alexnet5 = calculate_alexnet(all_recons_save_tensor, all_ground_truth_save_tensor)
        inception = calculate_inception_v3(all_recons_save_tensor, all_ground_truth_save_tensor)
        clip_ = calculate_clip(all_recons_save_tensor, all_ground_truth_save_tensor)
        efficientnet = calculate_efficientnet_b1(all_recons_save_tensor, all_ground_truth_save_tensor)
        swav = calculate_swav(all_recons_save_tensor, all_ground_truth_save_tensor)


    # save the results to a csv file
    df_metrics = pd.DataFrame({
        "Metric": [
            "alexnet2",
            "alexnet5",
            "inception",
            "clip_",
            "efficientnet",
            "swav",
            "pixcorr",
            "ssim",
            "all_fwd_acc_subset0",
            "all_bwd_acc_subset0",
            "all_fwd_acc_subset1",
            "all_bwd_acc_subset1"
        ],
        "Value": [
            alexnet2,
            alexnet5,
            inception,
            clip_,
            efficientnet,
            swav,
            pixcorr,
            ssim_,
            all_fwd_acc_subset0,
            all_bwd_acc_subset0,
            all_fwd_acc_subset1,
            all_bwd_acc_subset1
        ]
    })

    percentage_metrics = ["alexnet2", "alexnet5", "inception", "clip_", "retrieval"]
    lower_better_metrics = ["efficientnet", "swav"]
    higher_better_arrow = "↑"
    lower_better_arrow = "↓"

    # Format function
    def format_metric(metric, value):
        if metric in percentage_metrics:
            return f"{value * 100:.2f}% {higher_better_arrow}"
        elif metric in lower_better_metrics:
            return f"{value:.2f} {lower_better_arrow}"
        else:
            return f"{value:.2f} {higher_better_arrow}"

    # Apply formatting
    df_formatted = df_metrics.copy()
    df_formatted["Formatted"] = df_formatted.apply(lambda row: format_metric(row["Metric"], row["Value"]), axis=1)
    df_formatted.set_index("Metric", inplace=True)
    df_formatted.index.name = "Metric"

    # Print and save
    print(df_formatted[["Formatted"]])

    # df_formatted[["Formatted"]].to_csv(os.path.join(save_path, "metrics.csv"))