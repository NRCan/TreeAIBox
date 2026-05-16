import warnings
warnings.filterwarnings("ignore")

import torch
import numpy as np
import numpy_indexed as npi

from scipy.spatial import cKDTree
import numpy_groupies as npg
import json


def mergeshift(points,stem_cls,stem_id):
    seg_labels=np.zeros(len(points))
    stem_ind = stem_cls>0
    tree = cKDTree(points[stem_ind, :3])
    d, idx = tree.query(points[~stem_ind, :3])
    seg_labels[~stem_ind]=stem_id[stem_ind][idx]
    seg_labels[stem_ind]=stem_id[stem_ind]
    return seg_labels

def mergeremain(points,init_label,dec_res=0.2):
    points_min=np.min(points[:,:3],axis=0)
    _, points_u_idx, points_group_idx = np.unique(np.floor((points[:, :3] - points_min) / dec_res), axis=0, return_index=True,return_inverse=True)
    points_dec=points[points_u_idx]
    init_label_dec=init_label[points_u_idx]

    seg_labels=np.zeros(len(points_dec))
    exist_ind = init_label_dec>0
    tree = cKDTree(points_dec[exist_ind, :3])
    d, idx = tree.query(points_dec[~exist_ind, :3])
    seg_labels[~exist_ind]=init_label_dec[exist_ind][idx]
    seg_labels[exist_ind]=init_label_dec[exist_ind]
    return seg_labels[points_group_idx]

def crownOff(config_file, pcd, stem_id, model_path, use_cuda=True, progress_callback=lambda x: None):
    progress_callback(5)
    try:
        with open(config_file) as json_file:
            configs = json.load(json_file)
    except Exception as e:
        print(config_file)
        print("Cannot load config file:", e)
        return

    nbmat_sz = np.array(configs["model"]["voxel_number_in_block"])
    min_res = np.array(configs["model"]["voxel_resolution_in_meter"])

    try:
        from vox3DSegFormerRegression import Segformer
    except ImportError:
        from .vox3DSegFormerRegression import Segformer

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

    progress_callback(10)

    nb_tsz = int(nbmat_sz[0] * nbmat_sz[1] * nbmat_sz[2])
    pcd_min = np.min(pcd[:, :3], axis=0)

    block_ij = np.floor((pcd[:, :2] - pcd_min[:2]) / min_res[:2] / nbmat_sz[:2]).astype(np.int32)
    _, block_idx_groups = npi.group_by(block_ij, np.arange(len(block_ij)))

    nb_idxs = []
    nb_stems = []
    nb_pcd_idxs = []
    nb_inverse_idxs = []

    stem_cls=np.zeros(len(pcd),dtype=int)
    stem_cls[stem_id > 0]= 1.0

    for iter, idx in enumerate(block_idx_groups):
        columns_sp = pcd[idx, :]
        nb_pcd_idx = idx

        sp_min = np.min(columns_sp[:, :3], axis=0)
        nb_ijk = np.floor((columns_sp[:, :3] - sp_min) / min_res)
        nb_sel = np.all((nb_ijk < nbmat_sz) & (nb_ijk >= 0), axis=1)
        nb_ijk = nb_ijk[nb_sel]
        nb_pcd_idx = nb_pcd_idx[nb_sel]

        nb_idx = np.ravel_multi_index(np.transpose(nb_ijk.astype(np.int32)), nbmat_sz)
        nb_idx_u, nb_inverse_idx = np.unique(nb_idx, return_inverse=True)

        nb_stem_u = npg.aggregate(nb_inverse_idx, stem_cls[idx][nb_sel], func='mean', fill_value=0)  # can be some value between 0-1

        nb_idxs.append(nb_idx_u)
        nb_stems.append(nb_stem_u)
        nb_inverse_idxs.append(nb_inverse_idx)
        nb_pcd_idxs.append(nb_pcd_idx)

    progress_callback(15)

    pcd_pred = np.zeros([len(pcd), 3], dtype=np.float32)
    for k, idx in enumerate(nb_idxs):
        x = torch.zeros(nb_tsz, 2, dtype=torch.float)
        if len(idx) > 0:
            x[idx, 0] = 1.0  # could be distance to the nearest base center as the x
            x[idx, 1] = torch.from_numpy(nb_stems[k].astype(np.float32))  # could be distance to the nearest base center as the x

        x = torch.moveaxis(x.reshape((1, *nbmat_sz, 2)).float(), -1, 1)
        x = torch.swapaxes(x, -1, 2)

        with torch.no_grad():
            h = model(x.to(device))

        h_nonzero = torch.moveaxis(torch.unsqueeze(torch.moveaxis(torch.swapaxes(h, -1, 2), 1, -1).reshape((nb_tsz, 3))[idx, :],0), -1, 1)
        pcd_pred[nb_pcd_idxs[k], :] = np.moveaxis(h_nonzero.cpu().detach().numpy()[0], -1, 0)[nb_inverse_idxs[k]]

        progress_value = int(65 * k / len(nb_idxs)) + 15
        progress_callback(progress_value)

    init_labels = mergeshift(pcd[:,:3] + pcd_pred[:, :3] * min_res[:3],stem_cls,stem_id)

    pred_labels = mergeremain(pcd[:, :3], init_labels).astype(np.float32)
    return pred_labels
    # progress_callback(80)
    # return None


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
