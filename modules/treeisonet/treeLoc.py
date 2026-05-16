import warnings
warnings.filterwarnings("ignore")

import numpy as np
import json
import torch
import numpy_indexed as npi
import numpy_groupies as npg

from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from skimage import measure
# from skimage.filters import gaussian


# import matplotlib.pyplot as plt

# pip install scikit-learn laspy[lazrs] scipy numpy_indexed numpy_groupies commentjson timm scikit-image matplotlib einops plotly pandas
def nms3d(candidate_tops, nms_thresh=0.5, prioritize_height=True):
    """
    Perform non-maximum suppression on 3D tree top candidates.

    Args:
        candidate_tops: numpy array of shape (N, 4) where each row is [x, y, z, radius]
        iou_threshold: threshold for suppression based on distance/radius
        prioritize_height: if True, prioritize higher points (larger z values)
                           if False, prioritize larger radius points (original behavior)

    Returns:
        numpy array of selected tree tops after NMS
    """
    if len(candidate_tops) == 0:
        return np.empty((0, candidate_tops.shape[-1]))

    # Sort by z-coordinate (height) if prioritize_height is True, otherwise by radius
    if prioritize_height:
        order = candidate_tops[:, 2].argsort()[::-1]  # Higher z values (taller points) first
    else:
        order = candidate_tops[:, -1].argsort()[::-1]  # Larger radius first

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)

        # Calculate distances between current top and remaining candidates (xy-plane)
        current = candidate_tops[i, :2]
        remaining = candidate_tops[order[1:], :2]

        # Compute Euclidean distances in xy-plane
        distances = np.sqrt(np.sum((remaining - current) ** 2, axis=1))

        # Calculate distance threshold based on radii
        current_radius = candidate_tops[i, -1]
        remaining_radii = candidate_tops[order[1:], -1]

        # If points are closer than the sum of their radii * threshold, they overlap
        thresholds = (current_radius + remaining_radii) * nms_thresh

        # Find indices of boxes to keep
        inds = np.where(distances > thresholds)[0]

        # Update order indices
        order = order[inds + 1]  # +1 because we removed the first element

    return candidate_tops[keep]

def peakfinder(img,pcd_min,min_res):
    # markers = measure.label(clear_border(img > 0), background=-1)
    markers = measure.label(img > 0, background=-1)
    props = measure.regionprops(markers)
    coords=np.array([prop.centroid for prop in props])
    img_shape=img.shape

    if len(coords)>0:
        pt_coords=np.transpose([coords[:,1]*min_res[0]+pcd_min[0],(img_shape[0]-coords[:,0])*min_res[1]+pcd_min[1]])
    else:
        pt_coords=[]
    return pt_coords


def merge_patches(columns_min,min_res,nbmat_sz,patches, sp_mins):
    columns_max = np.max(np.array(sp_mins)[:, :2], axis=0) + min_res[:2] * nbmat_sz[:2]

    img_shape = np.floor((columns_max[:2] - columns_min[:2]) / min_res[:2]).astype(np.int32) + 1
    img_shape = img_shape[[1, 0]]

    img = np.zeros(img_shape.astype(np.int32))
    for k, patch in enumerate(patches):
        corner_i = columns_max[1] - sp_mins[k][1]
        corner_j = sp_mins[k][0] - columns_min[0]
        corner_ij = np.floor(np.array([corner_i, corner_j]) / min_res[[1, 0]]).astype(np.int32)
        img[corner_ij[0] - nbmat_sz[0] + 1:corner_ij[0] + 1,
        corner_ij[1]:corner_ij[1] + nbmat_sz[1]] = np.transpose(np.flip(patches[k], 1))
    return img

def treeLoc(config_file, pcd, model_path, use_cuda=True,if_stem=False,cutoff_thresh=1.0, progress_callback=lambda x: None, custom_resolution=np.array([0,0,0])):
    progress_callback(0)
    try:
        with open(config_file) as json_file:
            configs = json.load(json_file)
    except Exception as e:
        print(config_file)
        print("Cannot load config file:", e)
        return

    nbmat_sz = np.array(configs["model"]["voxel_number_in_block"])
    min_res = np.array(configs["model"]["voxel_resolution_in_meter"])
    
    if custom_resolution[0]>0 and custom_resolution[1]>0 and custom_resolution[2]>0:
        min_res=custom_resolution

    try:
        from vox3DSegFormerDetection import Segformer
    except ImportError:
        from .vox3DSegFormerDetection import Segformer

    model = Segformer(
        if_stem=if_stem,
        block3d_size=nbmat_sz,
        in_chans=1,
        num_classes=3,
        patch_size=configs["model"]["patch_size"],
        decoder_dim=configs["model"]["decoder_dim"],
        embed_dims=configs["model"]["channel_dims"],
        num_heads=configs["model"]["num_heads"],
        mlp_ratios=configs["model"]["MLP_ratios"],
        qkv_bias=configs["model"]["qkv_bias"],
        depths=configs["model"]["depths"],
        sr_ratios=configs["model"]["SR_ratios"],
        drop_rate=0.0,drop_path_rate=0.0,
    )

    device = "cuda" if use_cuda else "cpu"

    if use_cuda:
        model = model.cuda()
        state_dict = torch.load(model_path)
    else:
        state_dict = torch.load(model_path,map_location=torch.device('cpu'))

    model.max_accu = state_dict.get('max_accu', 0.0)
    if 'max_accu' in state_dict:
        state_dict.pop('max_accu')

    model.load_state_dict(state_dict)
    model.eval()

    progress_callback(5)

    nb_tsz = int(np.prod(nbmat_sz))
    pcd_min = np.min(pcd[:, :3], axis=0)

    if if_stem:
        cut_grid_res=5.0#rough tile size to filter lowest point and to cut the stem upper height
        tile_ij = np.floor((pcd[:, :2] - pcd_min[:2]) / cut_grid_res).astype(np.int32)
        _, tile_idx_groups = npi.group_by(tile_ij, np.arange(len(tile_ij)))
        filter_idx=[]
        for iter, idx in enumerate(tile_idx_groups):
            pcd_sp_min_z=np.min(pcd[idx, 2])
            filter_idx.append(idx[(pcd[idx, 2]-pcd_sp_min_z)<=(np.max(pcd[idx, 2])-pcd_sp_min_z)*cutoff_thresh])
        filter_idx=np.concatenate(filter_idx)
        # filter_idx=(pcd[:,2]-pcd_min[2])<(np.max(pcd[:,2])-pcd_min[2])*cutoff_thresh
        pcd=pcd[filter_idx]

    block_ij = np.floor((pcd[:, :2] - pcd_min[:2]) / min_res[:2] / nbmat_sz[:2]).astype(np.int32)
    _, block_idx_groups = npi.group_by(block_ij, np.arange(len(block_ij)))

    nb_idxs = []
    nb_pcd_idxs = []
    nb_inverse_idxs = []
    sp_mins = []

    for iter, idx in enumerate(block_idx_groups):
        columns_sp = pcd[idx, :]
        nb_pcd_idx = idx

        sp_min = np.min(columns_sp[:, :3], axis=0)
        nb_ijk = np.floor((columns_sp[:, :3] - sp_min) / min_res)
        nb_sel = np.all((nb_ijk < nbmat_sz) & (nb_ijk >= 0), axis=1)
        nb_ijk = nb_ijk[nb_sel]
        nb_pcd_idx = nb_pcd_idx[nb_sel]

        nb_idx = np.ravel_multi_index(np.transpose(nb_ijk.astype(np.int32)), nbmat_sz)
        nb_idx_u, _, nb_inverse_idx = np.unique(nb_idx, return_index=True, return_inverse=True)

        nb_idxs.append(nb_idx_u)
        nb_inverse_idxs.append(nb_inverse_idx)
        nb_pcd_idxs.append(nb_pcd_idx)
        sp_mins.append(sp_min)

    progress_callback(15)

    if if_stem:
        pred_patches = []
        for k, idx in enumerate(nb_idxs):
            x = torch.zeros(nb_tsz, 1)
            if len(idx) > 0:
                x[idx, :] = 1.0

            x = torch.moveaxis(x.reshape((1, *nbmat_sz, 1)).float(), -1, 1)
            x = torch.swapaxes(x, -1, 2)

            with torch.no_grad():
                h = model(x.to(device))
            h = torch.swapaxes(h, 2, -1)
            pred_patches.append((torch.softmax(h, 1)[0, 1].cpu().detach().numpy() > 0.1))

            progress_value = int(65 * k / len(nb_idxs)) + 15
            progress_callback(progress_value)

        pred_img = merge_patches(pcd_min, min_res, nbmat_sz, pred_patches, sp_mins)
        pred_coord = peakfinder(pred_img, pcd_min, min_res)

        tree = cKDTree(pcd[:,:2])
        pred_idxs = tree.query_ball_point(pred_coord[:, :2], 0.2,p=2)
        preds = np.array([pcd[pred_idx[np.argmin(pcd[pred_idx, 2])], :3] for pred_idx in pred_idxs])

    else:
        preds=np.zeros([len(pcd),5],dtype=np.float32)
        preds[:,:3]=pcd[:,:3]

        for k, idx in enumerate(nb_idxs):
            x = torch.zeros(nb_tsz, 1,dtype=torch.float)
            if len(idx) > 0:
                x[idx, :] = 1.0
            x = torch.moveaxis(x.reshape((1, *nbmat_sz, 1)).float(), -1, 1)
            x = torch.swapaxes(x, -1, 2)
            with torch.no_grad():
                pred_conf, pred_radius = model(x.to(device))
                # pred_conf, pred_radius = model(x)

                pred_conf_nonzero = torch.moveaxis(torch.unsqueeze(torch.moveaxis(torch.swapaxes(pred_conf, -1, 2), 1, -1).reshape((nb_tsz, 1))[idx, :], 0), -1, 1).detach().cpu().numpy()
                pred_radius_nonzero = torch.moveaxis(torch.unsqueeze(torch.moveaxis(torch.swapaxes(pred_radius, -1, 2), 1, -1).reshape((nb_tsz, 1))[idx, :], 0), -1, 1).detach().cpu().numpy()
                preds[nb_pcd_idxs[k],-2]=pred_conf_nonzero[0, 0][nb_inverse_idxs[k]]
                preds[nb_pcd_idxs[k],-1]=pred_radius_nonzero[0, 0][nb_inverse_idxs[k]] * min_res[0]

                progress_value = int(85 * k / len(nb_idxs)) + 15
                progress_callback(progress_value)

    return preds

def postPeakExtraction(preds_tops,K=5,max_gap=0.3,min_rad=0.2,nms_thresh=0.3,progress_callback=lambda x: None):
    point_count=len(preds_tops)
    kdtree = cKDTree(preds_tops[:, :3])
    nn_D, nn_idx = kdtree.query(preds_tops[:, :3], k=K)
    # Remove self-connections
    indices = nn_idx[:, 1:]
    nn_D = nn_D[:, 1:]

    progress_callback(40)

    # Create edge list
    eu = np.repeat(np.arange(point_count), K - 1)
    ev = indices.ravel()
    nn_D = nn_D.ravel()
    inlier_ind = nn_D < max_gap
    eu = eu[inlier_ind]
    ev = ev[inlier_ind]

    adjacency_matrix = csr_matrix((np.ones(len(eu), dtype=int), (eu, ev)), shape=(point_count, point_count))
    n_components, labels = connected_components(csgraph=adjacency_matrix, directed=False, connection='weak',return_labels=True)

    progress_callback(60)

    label_u, label_u_idx, label_inverse_idx = np.unique(labels, return_index=True, return_inverse=True)
    pred_top_radius = npg.aggregate(label_inverse_idx, preds_tops[:,-1], func=np.median, fill_value=0)
    pred_top_centroids = npg.aggregate(label_inverse_idx, preds_tops[:,:3],axis=0, func='mean', fill_value=0)

    # _, labels = np.unique(labels, axis=0, return_inverse=True)
    pred_candidate_tops=np.concatenate([pred_top_centroids,pred_top_radius[:,np.newaxis]],axis=-1)
    pred_candidate_tops = pred_candidate_tops[pred_candidate_tops[:, -1] > min_rad]
    pred_tops = nms3d(pred_candidate_tops,nms_thresh=nms_thresh)

    progress_callback(80)

    return pred_tops


if __name__ == "__main__":
    import os
    import glob
    import laspy

    use_cuda=True
    data_dir=r"C:\Users\trueb\Downloads"
    model_name="treeisonet_tls_boreal_treeloc_esegformer3D_128_10cm(GPU3GB)"
    # model_name="treeisonet_uav_mixedwood_treeloc_esegformer3D_128_10cm(GPU3GB)"
    # model_name="treeisonet_als_reclamation_treeloc_segformer3D_128_10cm(GPU4GB)"

    config_file=os.path.join(f"{model_name}.json")
    pcd_fnames = glob.glob(os.path.join(data_dir, "*.la*"))
    # pcd_fnames = glob.glob(os.path.join(data_dir, "jp9_riegl.laz"))
    # model_path = f"../../models/{model_name}.pth"
    model_path = rf"C:\Users\trueb\AppData\Local\CloudCompare\TreeAIBox\models\{model_name}.pth"

    out_path="output"

    if not os.path.exists(out_path):
        os.mkdir(out_path)

    for i, pcd_fname in enumerate(pcd_fnames):
        print(f"Processing {pcd_fname}...")
        las = laspy.open(pcd_fname).read()
        pcd = np.transpose(np.array([las.x, las.y, las.z]))  # las.point_format.dimension_names
        pcd_min=np.min(pcd[:,:3],0)
        pcd[:,:3]=pcd[:,:3]-pcd_min
        # preds=treeLoc(config_file,pcd,model_path,use_cuda=use_cuda,if_stem=True,cutoff_thresh=1.0)
        preds=treeLoc(config_file,pcd,model_path,use_cuda=use_cuda,if_stem=True,cutoff_thresh=0.2)
        if use_cuda:
            if i==0:
                free, total = torch.cuda.mem_get_info(torch.device("cuda"))
                mem_used_GB = (total - free) / 1024 ** 3
                print(f"Total GPU memory used: {mem_used_GB} GB")

        np.savetxt(os.path.join(out_path, "{}_tops.csv".format(os.path.basename(pcd_fname)[:-4])),preds+pcd_min)

        # min_rad = 0.2
        # conf_thresh = 0.3
        # pred_tops=postPeakExtraction(pred_conf_rads[pred_conf_rads[:,-2]>conf_thresh], K=5, max_gap=0.3, min_rad=min_rad, nms_thresh = 0.5)

        #
        # if len(pred_tops)>0:
        #     basefname=os.path.basename(pcd_fname)[:-4]
        #     outfname=os.path.join(out_path, "{}_treeloc.csv".format(basefname))
        #     np.savetxt(outfname,pred_tops)
        #
        #     if hasattr(las, 'veg_pred'):
        #         abg_ind=las.veg_pred>1
        #         preds=np.zeros([len(las.x),2])
        #         preds[abg_ind,:]=pred_conf_rads
        #     else:
        #         preds=pred_conf_rads
        #     las.add_extra_dim(laspy.ExtraBytesParams(name="pred_conf",type="float32",description="pred_conf"))
        #     las.add_extra_dim(laspy.ExtraBytesParams(name="pred_radius",type="float32",description="pred_radius"))
        #     las.pred_conf=preds[:,0]
        #     las.pred_radius=preds[:,1]
        #     las.write(os.path.join(out_path, "{}_top.laz".format(basefname)))
        #
        #     torch.cuda.empty_cache()
