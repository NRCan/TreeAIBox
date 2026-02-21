import warnings
warnings.filterwarnings("ignore")

import torch
import numpy as np
import numpy_indexed as npi

from scipy.spatial import cKDTree
import numpy_groupies as npg
import json


def mergeshift(points,stem_cls,stem_id):
    print("[crownOff] ========== MERGESHIFT: Stem-based Label Propagation ==========")
    print(f"[crownOff] Input: {len(points):,} points with stem classifications")
    
    seg_labels=np.zeros(len(points))
    stem_ind = stem_cls>0
    stem_count = np.sum(stem_ind)
    non_stem_count = len(points) - stem_count
    
    print(f"[crownOff] Stem points: {stem_count:,}, Non-stem points: {non_stem_count:,}")
    print(f"[crownOff] Building KDTree for {stem_count:,} stem points...")
    
    tree = cKDTree(points[stem_ind, :3])
    print(f"[crownOff] KDTree built successfully")
    
    print(f"[crownOff] Finding nearest stem for {non_stem_count:,} non-stem points...")
    
    # Process in batches to show progress
    batch_size = max(1000000, non_stem_count // 20)  # Process in ~20 batches
    non_stem_points = points[~stem_ind, :3]
    
    all_distances = np.zeros(non_stem_count)
    all_idx = np.zeros(non_stem_count, dtype=np.int32)
    
    for batch_num, start_idx in enumerate(range(0, non_stem_count, batch_size)):
        end_idx = min(start_idx + batch_size, non_stem_count)
        batch_points = non_stem_points[start_idx:end_idx]
        
        d, idx = tree.query(batch_points)
        all_distances[start_idx:end_idx] = d
        all_idx[start_idx:end_idx] = idx
        
        progress_pct = int(100 * end_idx / non_stem_count)
        print(f"[crownOff] Nearest neighbor search: {progress_pct}% ({end_idx:,}/{non_stem_count:,} points)")
    
    print(f"[crownOff] Nearest neighbor search complete")
    print(f"[crownOff] Nearest stem distances - Min: {np.min(all_distances):.3f}m, Max: {np.max(all_distances):.3f}m, Mean: {np.mean(all_distances):.3f}m")
    
    print(f"[crownOff] Assigning stem IDs to non-stem points...")
    seg_labels[~stem_ind]=stem_id[stem_ind][all_idx]
    seg_labels[stem_ind]=stem_id[stem_ind]
    
    print(f"[crownOff] Mergeshift complete - {len(seg_labels):,} labels assigned")
    print(f"[crownOff] ========== MERGESHIFT FINISHED ==========")
    return seg_labels

def mergeremain(points,init_label,dec_res=0.2):
    print("[crownOff] ========== MERGEREMAIN: Refinement for Unassigned Points ==========")
    print(f"[crownOff] Input: {len(points):,} points with initial labels (decimation resolution: {dec_res}m)")
    
    points_min=np.min(points[:,:3],axis=0)
    print(f"[crownOff] Decimating point cloud (grouping points within {dec_res}m grid)...")
    
    _, points_u_idx, points_group_idx = np.unique(np.floor((points[:, :3] - points_min) / dec_res), axis=0, return_index=True,return_inverse=True)
    print(f"[crownOff] Decimation complete: {len(points_u_idx):,} unique points from {len(points):,} original")
    
    points_dec=points[points_u_idx]
    init_label_dec=init_label[points_u_idx]

    seg_labels=np.zeros(len(points_dec))
    exist_ind = init_label_dec>0
    labeled_count = np.sum(exist_ind)
    unlabeled_count = len(points_dec) - labeled_count
    
    print(f"[crownOff] Labeled points: {labeled_count:,}, Unlabeled points: {unlabeled_count:,}")
    
    if unlabeled_count > 0:
        print(f"[crownOff] Building KDTree for {labeled_count:,} labeled points...")
        tree = cKDTree(points_dec[exist_ind, :3])
        print(f"[crownOff] KDTree built successfully")
        
        print(f"[crownOff] Finding nearest labeled point for {unlabeled_count:,} unlabeled points...")
        
        # Process in batches to show progress
        batch_size = max(50000, unlabeled_count // 20)  # Process in ~20 batches
        unlabeled_points = points_dec[~exist_ind, :3]
        
        all_distances = np.zeros(unlabeled_count)
        all_idx = np.zeros(unlabeled_count, dtype=np.int32)
        
        for batch_num, start_idx in enumerate(range(0, unlabeled_count, batch_size)):
            end_idx = min(start_idx + batch_size, unlabeled_count)
            batch_points = unlabeled_points[start_idx:end_idx]
            
            d, idx = tree.query(batch_points)
            all_distances[start_idx:end_idx] = d
            all_idx[start_idx:end_idx] = idx
            
            progress_pct = int(100 * end_idx / unlabeled_count)
            print(f"[crownOff] Refinement search: {progress_pct}% ({end_idx:,}/{unlabeled_count:,} points)")
        
        print(f"[crownOff] Nearest neighbor search complete")
        print(f"[crownOff] Nearest labeled distances - Min: {np.min(all_distances):.3f}m, Max: {np.max(all_distances):.3f}m, Mean: {np.mean(all_distances):.3f}m")
        
        print(f"[crownOff] Assigning labels to {unlabeled_count:,} unlabeled points...")
        seg_labels[~exist_ind]=init_label_dec[exist_ind][all_idx]
    else:
        print(f"[crownOff] All points already labeled - no refinement needed")
    
    seg_labels[exist_ind]=init_label_dec[exist_ind]
    
    print(f"[crownOff] Mapping refined labels back to original point cloud...")
    result = seg_labels[points_group_idx]
    
    print(f"[crownOff] Mergeremain complete - {len(result):,} labels refined")
    print(f"[crownOff] ========== MERGEREMAIN FINISHED ==========")
    return result

def crownOff(config_file, pcd, stem_id, model_path, use_cuda=True, progress_callback=lambda x: None):
    progress_callback(5)
    print("[crownOff] ========== CROWNOFF PROCESSING STARTED ==========")
    print(f"[crownOff] Input parameters:")
    print(f"[crownOff]   - Config file: {config_file}")
    print(f"[crownOff]   - Point cloud shape: {pcd.shape}")
    print(f"[crownOff]   - Stem ID array length: {len(stem_id)}")
    print(f"[crownOff]   - Model path: {model_path}")
    print(f"[crownOff]   - Use CUDA: {use_cuda}")
    
    try:
        print("[crownOff] Loading configuration file...")
        with open(config_file) as json_file:
            configs = json.load(json_file)
        print(f"[crownOff] Configuration loaded successfully")
    except Exception as e:
        print(f"[crownOff] ERROR: Cannot load config file: {e}")
        print(config_file)
        return

    nbmat_sz = np.array(configs["model"]["voxel_number_in_block"])
    min_res = np.array(configs["model"]["voxel_resolution_in_meter"])
    print(f"[crownOff] Model configuration:")
    print(f"[crownOff]   - Voxel block size: {nbmat_sz}")
    print(f"[crownOff]   - Voxel resolution (m): {min_res}")

    try:
        from vox3DSegFormerRegression import Segformer
    except ImportError:
        from .vox3DSegFormerRegression import Segformer

    print("[crownOff] Creating neural network model...")
    model = Segformer(
        block3d_size=nbmat_sz,
        in_chans=2,
        out_chans=3,
        patch_size=configs["model"]["patch_size"],
        decoder_dim=configs["model"]["decoder_dim"],
        embed_dims=configs["model"]["channel_dims"],
        num_heads=configs["model"]["num_heads"],
        mlp_ratios=configs["model"]["MLP_ratios"],
        qkv_bias=configs["model"]["qkv_bias"],
        depths=configs["model"]["depths"],
        sr_ratios=configs["model"]["SR_ratios"],
        drop_rate=0.0, drop_path_rate=0.0
    )
    print(f"[crownOff] Model architecture created successfully")
    
    device = "cuda" if use_cuda else "cpu"
    print(f"[crownOff] Device: {device.upper()}")

    print("[crownOff] Loading pre-trained weights...")
    if use_cuda:
        model = model.cuda()
        state_dict = torch.load(model_path)
    else:
        state_dict = torch.load(model_path, map_location=torch.device('cpu'))
    
    model.max_accu = state_dict.get('max_accu', 0.0)
    if 'max_accu' in state_dict:
        state_dict.pop('max_accu')
    model.load_state_dict(state_dict)
    model.eval()
    print(f"[crownOff] Model weights loaded and set to evaluation mode")

    progress_callback(10)

    print("[crownOff] ========== DATA PREPARATION PHASE ==========")
    nb_tsz = int(nbmat_sz[0] * nbmat_sz[1] * nbmat_sz[2])
    pcd_min = np.min(pcd[:, :3], axis=0)
    print(f"[crownOff] Point cloud min coordinates: {pcd_min}")

    print(f"[crownOff] Calculating block assignments for {len(pcd):,} points...")
    block_ij = np.floor((pcd[:, :2] - pcd_min[:2]) / min_res[:2] / nbmat_sz[:2]).astype(np.int32)
    _, block_idx_groups = npi.group_by(block_ij, np.arange(len(block_ij)))
    print(f"[crownOff] Points grouped into {len(block_idx_groups):,} blocks")

    nb_idxs = []
    nb_stems = []
    nb_pcd_idxs = []
    nb_inverse_idxs = []

    stem_cls = np.zeros(len(pcd), dtype=int)
    stem_cls[stem_id > 0] = 1.0
    stem_point_count = np.sum(stem_cls > 0)
    print(f"[crownOff] Points with stem classification: {stem_point_count:,} / {len(pcd):,}")

    print(f"[crownOff] Processing blocks and extracting voxel features...")
    for iter, idx in enumerate(block_idx_groups):
        if iter % max(1, len(block_idx_groups) // 10) == 0:
            print(f"[crownOff]   Block {iter+1}/{len(block_idx_groups)} - Processing {len(idx):,} points")
        
        columns_sp = pcd[idx, :]
        nb_pcd_idx = idx

        sp_min = np.min(columns_sp[:, :3], axis=0)
        nb_ijk = np.floor((columns_sp[:, :3] - sp_min) / min_res)
        nb_sel = np.all((nb_ijk < nbmat_sz) & (nb_ijk >= 0), axis=1)
        nb_ijk = nb_ijk[nb_sel]
        nb_pcd_idx = nb_pcd_idx[nb_sel]

        nb_idx = np.ravel_multi_index(np.transpose(nb_ijk.astype(np.int32)), nbmat_sz)
        nb_idx_u, nb_inverse_idx = np.unique(nb_idx, return_inverse=True)

        nb_stem_u = npg.aggregate(nb_inverse_idx, stem_cls[idx][nb_sel], func='mean', fill_value=0)

        nb_idxs.append(nb_idx_u)
        nb_stems.append(nb_stem_u)
        nb_inverse_idxs.append(nb_inverse_idx)
        nb_pcd_idxs.append(nb_pcd_idx)

    print(f"[crownOff] Block processing complete - {len(nb_idxs):,} blocks prepared")
    progress_callback(15)

    print("[crownOff] ========== NEURAL NETWORK INFERENCE PHASE ==========")
    print(f"[crownOff] Running inference on {len(nb_idxs):,} blocks...")
    
    pcd_pred = np.zeros([len(pcd), 3], dtype=np.float32)
    for k, idx in enumerate(nb_idxs):
        # Progress reporting every 10% of blocks
        if k % max(1, len(nb_idxs) // 10) == 0:
            print(f"[crownOff]   Batch {k+1}/{len(nb_idxs)} - Processing block with {len(idx):,} voxels")
        
        x = torch.zeros(nb_tsz, 2, dtype=torch.float)
        if len(idx) > 0:
            x[idx, 0] = 1.0  # occupied voxel indicator
            x[idx, 1] = torch.from_numpy(nb_stems[k].astype(np.float32))  # stem presence

        x = torch.moveaxis(x.reshape((1, *nbmat_sz, 2)).float(), -1, 1)
        x = torch.swapaxes(x, -1, 2)

        with torch.no_grad():
            h = model(x.to(device))

        h_nonzero = torch.moveaxis(torch.unsqueeze(torch.moveaxis(torch.swapaxes(h, -1, 2), 1, -1).reshape((nb_tsz, 3))[idx, :], 0), -1, 1)
        pcd_pred[nb_pcd_idxs[k], :] = np.moveaxis(h_nonzero.cpu().detach().numpy()[0], -1, 0)[nb_inverse_idxs[k]]

        progress_value = int(65 * k / len(nb_idxs)) + 15
        progress_callback(progress_value)

    print(f"[crownOff] Neural network inference complete")
    print("[crownOff] ========== POST-PROCESSING PHASE ==========")
    print(f"[crownOff] Phase 1: Merging predictions and shifting coordinates...")
    print(f"[crownOff] Applying coordinate shifts from neural network predictions...")
    
    init_labels = mergeshift(pcd[:, :3] + pcd_pred[:, :3] * min_res[:3], stem_cls, stem_id)
    print(f"[crownOff] Initial label merging complete - {len(init_labels):,} labels assigned")

    print(f"[crownOff] Phase 2: Refining predictions for remaining points...")
    pred_labels = mergeremain(pcd[:, :3], init_labels).astype(np.float32)
    
    crown_count = np.sum(pred_labels > 0)
    non_crown_count = len(pred_labels) - crown_count
    print(f"[crownOff] Prediction refinement complete:")
    print(f"[crownOff]   - Crown points: {crown_count:,}")
    print(f"[crownOff]   - Non-crown points: {non_crown_count:,}")
    print(f"[crownOff]   - Total points: {len(pred_labels):,}")
    
    progress_callback(85)
    print("[crownOff] ========== CROWNOFF PROCESSING COMPLETE ==========")
    
    return pred_labels


if __name__ == "__main__":
    import os
    import glob
    import laspy

    use_cuda=True

    data_dir=r"F:\prj\CC2\comp\cc-TreeAIBox-plugin\data\new"
    # model_name="treeisonet_tls_boreal_treeloc_esegformer3D_128_8cm(GPU4GB)"
    # model_name="treeisonet_tls_boreal_crownoff_esegformer3D_128_15cm(GPU4GB)"
    model_name="treeisonet_uav_mixedwood_crownoff_esegformer3D_128_15cm(GPU4GB)"


    config_file=os.path.join(f"{model_name}.json")
    pcd_fnames = glob.glob(os.path.join(data_dir, "*.la*"))
    model_path = f"../../models/{model_name}.pth"

    out_path="output"
    if not os.path.exists(out_path):
        os.mkdir(out_path)

    for i, pcd_fname in enumerate(pcd_fnames):
        print(f"Processing {pcd_fname}...")
        las = laspy.open(pcd_fname).read()
        pcd = np.transpose(np.array([las.x, las.y, las.z]))  # las.point_format.dimension_names
        # pcd[:,:3]=pcd[:,:3]-np.min(pcd[:,:3],0)
        pcd[:,:3]=pcd[:,:3]-np.min(pcd[:,:3],0)

        stem_id=las.itc_edit
        # stem_id[las.stemcls<2]=0

        stem_id[las.classification!=4]=0

        preds=crownOff(config_file,pcd,stem_id,model_path,use_cuda=use_cuda)
        if use_cuda:
            if i==0:
                free, total = torch.cuda.mem_get_info(torch.device("cuda"))
                mem_used_GB = (total - free) / 1024 ** 3
                print(f"Total GPU memory used: {mem_used_GB} GB")

        las.add_extra_dim(laspy.ExtraBytesParams(name="crownoff",type="int32",description="pred_conf"))
        las.crownoff=preds
        las.write(os.path.join(out_path, "{}_crownoff.laz".format(os.path.basename(pcd_fname)[:-4])))

        torch.cuda.empty_cache()
