import numpy as np
import numpy_indexed as npi
import json

import torch


def sliding_blocks_point_indices(pts, block_size, overlap_ratio):
    """
    Slice 2D or 3D points into overlapping blocks.

    Parameters
    ----------
    pts : (N, 2) or (N, 3) array
        Input points, either 2D or 3D.
    block_size : sequence of length 2 or 3
        Size of each block in each dimension.
    overlap_ratio : float in [0,1)
        Fractional overlap between adjacent blocks.

    Returns
    -------
    origins : (M, 2) or (M, 3) array
        Array of each block’s lower-corner coordinates.
    groups : list of ndarrays
        For each block, an array of point indices that fall inside it.
    """
    pts = np.asarray(pts, float)
    ndim = pts.shape[1]
    if ndim not in (2, 3):
        raise ValueError("Only 2D or 3D points are supported (shape (N,2) or (N,3)).")

    bs = np.asarray(block_size, float)
    if bs.size != ndim:
        raise ValueError(f"block_size must have length {ndim}.")
    stride = bs * (1.0 - overlap_ratio)

    p_min = pts.min(axis=0)
    p_max = pts.max(axis=0)
    steps = np.floor((p_max - p_min - bs) / stride).astype(int) + 1
    dims = steps + 1  # number of blocks along each axis

    # Compute each point’s “primary” block index along each dimension
    rel = (pts - p_min) / stride
    idx0 = np.floor(rel).astype(int)  # shape (N, ndim)

    # Prepare indices for the current block and the previous block (clipped)
    ixs = np.clip(np.stack([idx0[:, 0], idx0[:, 0] - 1], axis=1), 0, dims[0] - 1)
    iys = np.clip(np.stack([idx0[:, 1], idx0[:, 1] - 1], axis=1), 0, dims[1] - 1)
    N = pts.shape[0]

    if ndim == 3:
        izs = np.clip(np.stack([idx0[:, 2], idx0[:, 2] - 1], axis=1), 0, dims[2] - 1)
        combos = [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]
        ix = np.stack([ixs[np.arange(N), a] for a, _, _ in combos], axis=1)
        iy = np.stack([iys[np.arange(N), b] for _, b, _ in combos], axis=1)
        iz = np.stack([izs[np.arange(N), c] for _, _, c in combos], axis=1)

        cond_x = (pts[:, 0, None] >= p_min[0] + ix * stride[0]) & (pts[:, 0, None] < p_min[0] + ix * stride[0] + bs[0])
        cond_y = (pts[:, 1, None] >= p_min[1] + iy * stride[1]) & (pts[:, 1, None] < p_min[1] + iy * stride[1] + bs[1])
        cond_z = (pts[:, 2, None] >= p_min[2] + iz * stride[2]) & (pts[:, 2, None] < p_min[2] + iz * stride[2] + bs[2])
        mask = cond_x & cond_y & cond_z

        block_ids = (ix * (dims[1] * dims[2]) + iy * dims[2] + iz).ravel()[mask.ravel()]
    else:
        # 2D case: only 4 combinations of (ix,iy)
        combos = [(a, b) for a in (0, 1) for b in (0, 1)]
        ix = np.stack([ixs[np.arange(N), a] for a, _ in combos], axis=1)
        iy = np.stack([iys[np.arange(N), b] for _, b in combos], axis=1)

        cond_x = (pts[:, 0, None] >= p_min[0] + ix * stride[0]) & (pts[:, 0, None] < p_min[0] + ix * stride[0] + bs[0])
        cond_y = (pts[:, 1, None] >= p_min[1] + iy * stride[1]) & (pts[:, 1, None] < p_min[1] + iy * stride[1] + bs[1])
        mask = cond_x & cond_y

        block_ids = (ix * dims[1] + iy).ravel()[mask.ravel()]

    point_ids = np.repeat(np.arange(N), mask.shape[1])[mask.ravel()]
    unique_bids, groups = npi.group_by(block_ids, point_ids)

    # Decode block origins
    if ndim == 3:
        ix_u = unique_bids // (dims[1] * dims[2])
        rem = unique_bids % (dims[1] * dims[2])
        iy_u = rem // dims[2]
        iz_u = rem % dims[2]
        origins = np.vstack([
            p_min[0] + ix_u * stride[0],
            p_min[1] + iy_u * stride[1],
            p_min[2] + iz_u * stride[2],
        ]).T
    else:
        ix_u = unique_bids // dims[1]
        iy_u = unique_bids % dims[1]
        origins = np.vstack([
            p_min[0] + ix_u * stride[0],
            p_min[1] + iy_u * stride[1],
        ]).T

    return origins, [np.array(g, int) for g in groups]

def filterPoints(config_file, pcd, model_path, if_bottom_only=True,use_efficient=True,use_cuda=True, progress_callback=lambda x: None):
    progress_callback(10)
    print(f"[filterPoints] Starting component filtering")
    print(f"[filterPoints] Config file: {config_file}")
    print(f"[filterPoints] Model path: {model_path}")
    print(f"[filterPoints] Input point cloud shape: {pcd.shape}")
    print(f"[filterPoints] Using GPU: {use_cuda}")
    
    # laod variables from the config file (e.g. woodcls_branch_tls_segformer3D_112_4cm(GPU8GB).json
    try:
        print(f"[filterPoints] Loading config file...")
        with open(config_file) as json_file:
            configs = json.load(json_file)
        print(f"[filterPoints] Config file loaded successfully")
    except Exception as e:
        print(config_file)
        print("Cannot load config file:", e)
        return

    nbmat_sz = np.array(configs["model"]["voxel_number_in_block"])
    min_res = np.array(configs["model"]["voxel_resolution_in_meter"])
    num_classes = configs["model"]["num_classes"]+1
    print(f"[filterPoints] Block size: {nbmat_sz}, Resolution: {min_res}, Classes: {num_classes}")
    
    #define and load the 3D segformer model
    print(f"[filterPoints] Importing model architecture (efficient={use_efficient})...")
    if use_efficient:
        try:
            from vox3DESegFormer import Segformer#efficient segformer
        except ImportError:
            from .vox3DESegFormer import Segformer
    else:
        try:
            from vox3DSegFormer import Segformer
        except ImportError:
            from .vox3DSegFormer import Segformer
    
    print(f"[filterPoints] Creating model instance...")
    model = Segformer(
        block3d_size=nbmat_sz,
        in_chans=1,
        num_classes=num_classes,
        patch_size=configs["model"]["patch_size"],
        decoder_dim=configs["model"]["decoder_dim"],
        embed_dims=configs["model"]["channel_dims"],
        num_heads=configs["model"]["num_heads"],
        mlp_ratios=configs["model"]["MLP_ratios"],
        qkv_bias=configs["model"]["qkv_bias"],
        depths=configs["model"]["depths"],
        sr_ratios=configs["model"]["SR_ratios"],
        drop_rate=0.0,
        drop_path_rate=0.0,
    )
    print(f"[filterPoints] Model instance created")

    device = "cuda" if use_cuda else "cpu"
    print(f"[filterPoints] Using device: {device}")
    
    if use_cuda:
        print(f"[filterPoints] GPU Information:")
        print(f"[filterPoints]   Device count: {torch.cuda.device_count()}")
        print(f"[filterPoints]   Current device: {torch.cuda.current_device()}")
        print(f"[filterPoints]   Device name: {torch.cuda.get_device_name(0)}")
        print(f"[filterPoints]   CUDA available: {torch.cuda.is_available()}")
        print(f"[filterPoints]   Memory allocated: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
        print(f"[filterPoints]   Memory reserved: {torch.cuda.memory_reserved() / 1e9:.2f} GB")
        
        print(f"[filterPoints] Moving model to GPU...")
        model = model.cuda()
        print(f"[filterPoints]   Memory after model.cuda(): {torch.cuda.memory_allocated() / 1e9:.2f} GB")
        
        print(f"[filterPoints] Loading state dict from {model_path}...")
        state_dict = torch.load(model_path)
        print(f"[filterPoints] State dict loaded")
    else:
        print(f"[filterPoints] Loading state dict to CPU from {model_path}...")
        state_dict = torch.load(model_path,map_location=torch.device('cpu'))
        print(f"[filterPoints] State dict loaded to CPU")

    model.max_accu = state_dict.get('max_accu', 0.0)
    if 'max_accu' in state_dict:
        state_dict.pop('max_accu')

    model.best_mIoU = state_dict.get('best_mIoU', 0.0)
    if 'best_mIoU' in state_dict:
        state_dict.pop('best_mIoU')

    print(f"[filterPoints] Loading state dict into model...")
    model.load_state_dict(state_dict)
    print(f"[filterPoints] Setting model to eval mode...")
    model.eval()
    print(f"[filterPoints] Model loaded and ready")

    nb_tsz = int(np.prod(nbmat_sz))
    print(f"[filterPoints] Block tensor size: {nb_tsz}")

    #voxelize
    if if_bottom_only:
        cut_dim=2
    else:
        cut_dim=3
    
    print(f"[filterPoints] Starting voxelization (cut_dim={cut_dim})...")
    print(f"[filterPoints] Point cloud shape: {pcd.shape}, cut_dim: {cut_dim}")
    _, block_idx_groups = sliding_blocks_point_indices(pcd[:, :cut_dim], min_res[:cut_dim] * nbmat_sz[:cut_dim], overlap_ratio=0.1)
    print(f"[filterPoints] Voxelization complete. Number of blocks: {len(block_idx_groups)}")

    nb_idxs = []
    nb_pcd_idxs = []
    nb_inverse_idxs = []

    print(f"[filterPoints] Processing {len(block_idx_groups)} blocks to extract voxel indices...")
    for idx_block, idx in enumerate(block_idx_groups):
        if idx_block % max(1, len(block_idx_groups) // 10) == 0:
            print(f"[filterPoints]   Processed {idx_block}/{len(block_idx_groups)} blocks")
        
        columns_sp = pcd[idx, :]
        nb_pcd_idx = idx

        sp_min = np.min(columns_sp[:, :3], axis=0)
        nb_ijk = np.floor((columns_sp[:, :3] - sp_min) / min_res)
        nb_sel = np.all((nb_ijk < nbmat_sz) & (nb_ijk >= 0), axis=1)
        nb_ijk = nb_ijk[nb_sel]
        nb_pcd_idx = nb_pcd_idx[nb_sel]

        nb_idx = np.ravel_multi_index(nb_ijk.astype(np.int32).T, nbmat_sz)
        nb_idx_u, nb_inverse_idx = np.unique(nb_idx, return_inverse=True)

        nb_idxs.append(nb_idx_u)#indicies of unique voxels from each block
        nb_inverse_idxs.append(nb_inverse_idx)#indices used to reproject the unique voxels to original order
        nb_pcd_idxs.append(nb_pcd_idx)#within-voxel point indices from the point cloud
    
    print(f"[filterPoints] Voxel index extraction complete")

    progress_callback(15)

    #apply the DL model blockwisely
    if num_classes>3:
        print(f"[filterPoints] Starting multi-class inference ({num_classes} classes)")
        pcd_pred = np.full(len(pcd), dtype=int, fill_value=num_classes-1)
        
        total_nbs = len(nb_idxs)
        print(f"[filterPoints] Processing {total_nbs} blocks with DL model...")
        for i in range(total_nbs):
            if i % max(1, total_nbs // 20) == 0:
                if use_cuda:
                    print(f"[filterPoints]   Block {i+1}/{total_nbs} ({100*i/total_nbs:.1f}%) - GPU Mem: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
                else:
                    print(f"[filterPoints]   Block {i+1}/{total_nbs} ({100*i/total_nbs:.1f}%)")
            
            nb_idx = nb_idxs[i]

            x = torch.zeros(nb_tsz, 1)
            if len(nb_idx) > 0:
                x[nb_idx, :] = 1.0

            x = torch.swapaxes(torch.moveaxis(x.reshape((1, *nbmat_sz, 1)).float(), -1, 1), -1, 2)
            with torch.no_grad():
                try:
                    h = model(x.to(device))
                except RuntimeError as e:
                    print(f"[filterPoints] ERROR: GPU/model inference failed at block {i}: {e}")
                    print(f"[filterPoints] Input tensor shape: {x.shape}")
                    if use_cuda:
                        print(f"[filterPoints] GPU Mem when error: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
                    raise

            h_nonzero = torch.moveaxis(torch.unsqueeze(torch.moveaxis(torch.swapaxes(h, -1, 2), 1, -1).reshape((nb_tsz, num_classes))[nb_idx, :],0), -1, 1)
            h_nonzero = torch.argmax(h_nonzero[0], dim=0)

            nb_pred = h_nonzero.cpu().detach().numpy()
            pcd_pred[nb_pcd_idxs[i]] = nb_pred[nb_inverse_idxs[i]]

            progress_value = int(85 * i / total_nbs) + 15
            progress_callback(progress_value)
        
        print(f"[filterPoints] Multi-class inference complete")
        progress_callback(100)
        return pcd_pred.astype(np.int32)#int(1,2)
    
    else:#binary case
        print(f"[filterPoints] Starting binary classification inference")
        pcd_pred = np.full(len(pcd), dtype=bool, fill_value=False)
            

        total_nbs = len(nb_idxs)
        print(f"[filterPoints] Processing {total_nbs} blocks with DL model...")
        for i in range(total_nbs):
            if i % max(1, total_nbs // 20) == 0:
                if use_cuda:
                    print(f"[filterPoints]   Block {i+1}/{total_nbs} ({100*i/total_nbs:.1f}%) - GPU Mem: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
                else:
                    print(f"[filterPoints]   Block {i+1}/{total_nbs} ({100*i/total_nbs:.1f}%)")
            
            nb_idx = nb_idxs[i]

            x = torch.zeros(nb_tsz, 1)
            if len(nb_idx) > 0:
                x[nb_idx, :] = 1.0

            x = torch.swapaxes(torch.moveaxis(x.reshape((1, *nbmat_sz, 1)).float(), -1, 1), -1, 2)
            with torch.no_grad():
                try:
                    h = model(x.to(device))
                except RuntimeError as e:
                    print(f"[filterPoints] ERROR: GPU/model inference failed at block {i}: {e}")
                    print(f"[filterPoints] Input tensor shape: {x.shape}")
                    if use_cuda:
                        print(f"[filterPoints] GPU Mem when error: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
                    raise

            h_nonzero = torch.moveaxis(torch.unsqueeze(torch.moveaxis(torch.swapaxes(h, -1, 2), 1, -1).reshape((nb_tsz, num_classes))[nb_idx, :],0), -1, 1)
            h_nonzero = torch.argmax(h_nonzero[0], dim=0)

            nb_pred = h_nonzero.cpu().detach().numpy()
            pcd_pred[nb_pcd_idxs[i]] = pcd_pred[nb_pcd_idxs[i]] | (nb_pred[nb_inverse_idxs[i]]>1)#Flag the binary over the overlapped area

            progress_value = int(85 * i / total_nbs) + 15
            progress_callback(progress_value)

        print(f"[filterPoints] Binary classification inference complete")
        # pcd_pred[pcd_pred > 2.0] = 2.0
        if if_bottom_only:
            print(f"[filterPoints] Applying bottom-only filter...")
            seen = np.zeros_like(pcd_pred, dtype=bool)
            seen[np.concatenate(nb_pcd_idxs)] = True  # mark every index that was ever visited
            pcd_pred[~seen] = True
        
        print(f"[filterPoints] Processing complete")
        progress_callback(100)
        return pcd_pred.astype(np.int32)+1#bool(False,True) to int(1,2)




#Test
if __name__ == "__main__":
    import os
    import glob
    import laspy


    # model_name="treefiltering_als_esegformer3D_128_15cm(GPU3GB)"
    model_name="treefiltering_tls_esegformer3D_128_8cm(GPU3GB)"
    # model_name="treefiltering_als_esegformer3D_128_50cm(GPU3GB)"
    # model_name="treefiltering_uav_esegformer3D_128_12cm(GPU3GB)"
    # model_name="treeisonet_uav_mixedwood_stemcls_esegformer3D_128_8cm(GPU3GB)"


    config_file=os.path.join(f"{model_name}.json")

    # data_dir=r"D:\xzx\prj\cc-TreeAIBox-plugin\data\tmp"
    data_dir=r"F:\prj\CC2\comp\cc-TreeAIBox-plugin\data\new"

    pcd_fnames = glob.glob(os.path.join(data_dir, "*.la*"))
    model_path = f"../../models/{model_name}.pth"

    out_path="output"
    out_attr="woodcls"

    use_cuda=True

    if not os.path.exists(out_path):
        os.mkdir(out_path)

    for i, pcd_fname in enumerate(pcd_fnames):
        print(f"Processing {pcd_fname}...")
        las = laspy.open(pcd_fname).read()
        pcd = np.transpose(np.array([las.x, las.y, las.z]))  # las.point_format.dimension_names
        # pcd_pred=filterPoints("F:\\prj\\CC2\\comp\\cc-TreeAIBox-plugin\\modules\\treeisonet\\"+config_file,pcd,model_path,if_bottom_only=False,use_efficient="esegformer" in model_name,use_cuda=use_cuda)
        pcd_pred=filterPoints("F:\\prj\\CC2\\comp\\cc-TreeAIBox-plugin\\modules\\filter\\"+config_file,pcd,model_path,if_bottom_only=False,use_efficient="esegformer" in model_name,use_cuda=use_cuda)

        if use_cuda:
            if i==0:
                free, total = torch.cuda.mem_get_info(torch.device("cuda"))
                mem_used_GB = (total - free) / 1024 ** 3
                print(f"Total GPU memory used: {mem_used_GB} GB")

        las.add_extra_dim(laspy.ExtraBytesParams(name=out_attr, type="int32", description="Predicted points"))
        setattr(las,out_attr,pcd_pred)
        las.write(os.path.join(out_path, f"{os.path.basename(pcd_fname)[:-4]}_{out_attr}.laz"))
        torch.cuda.empty_cache()