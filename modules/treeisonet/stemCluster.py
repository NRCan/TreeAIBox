import numpy as np
import numpy_indexed as npi

from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import dijkstra
from sklearn.mixture import BayesianGaussianMixture

def create_sparse_graph(points, k=10, max_distance=np.inf):
    """
    Create a sparse graph based on k-nearest neighbors within max_distance.

    :param points: numpy array of shape (n_points, n_dimensions)
    :param k: number of nearest neighbors to consider
    :param max_distance: maximum distance for connections
    :return: scipy.sparse.csr_matrix representing the graph
    """
    kdtree = cKDTree(points)
    distances, indices = kdtree.query(points, k=k + 1, distance_upper_bound=max_distance)

    # Remove self-connections (first column)
    distances = distances[:, 1:]
    indices = indices[:, 1:]

    # Create row indices
    row_ind = np.repeat(np.arange(len(points)), k)
    # Flatten column indices and distances
    col_ind = indices.ravel()
    data = distances.ravel()

    # Remove any remaining infinite distances
    valid = np.isfinite(data)
    row_ind = row_ind[valid]
    col_ind = col_ind[valid]
    data = data[valid]
    # data[data<min_gap]=0.0

    graph = csr_matrix((data, (row_ind, col_ind)), shape=(len(points), len(points)))
    return (graph + graph.T) / 2  # Make symmetric

def decimate_pcd(points,min_res):
    _, block_idx_uidx, block_inverse_idx = np.unique(np.floor(points[:, :3] / min_res).astype(np.int32), axis=0,return_index=True, return_inverse=True)
    return block_idx_uidx,block_inverse_idx

def create_node_graph(points,k=10,max_distance=0.4):#max_allowed distance for a component not to be considered as an outlier

    node_total=len(np.unique(points[:,-1]))# the last column of the points is the node ID
    _, v_group = npi.group_by(points[:, -1].astype(np.int32), np.arange(len(points[:, -1])))
    centroids = np.array([np.mean(points[idx, :3], 0) for idx in v_group])#extract the mean value of each node centroid
    n_centroids = len(centroids)
    kdtree = cKDTree(centroids[:, :2])
    _, indices = kdtree.query(centroids[:, :2], k=min(k + 1,len(centroids)))#create a table with pairs of closest K+1 nodes
    distance_pairs = np.zeros([len(centroids) * k, 4])#x,y,z, distance in 2D, and distance in 3D
    for i, v in enumerate(v_group):
        nn_idx = indices[i, 1:]
        tree = cKDTree(points[v, :3])
        for j, nv in enumerate(nn_idx):
            nn_dist, nn_j = tree.query(points[v_group[nv], :3], k=1)
            nn_ij = np.argmin(nn_dist)
            pts1=points[v_group[nv], :3][nn_ij]
            pts2=points[v, :3][nn_j[nn_ij]]
            nn_dist2d=np.linalg.norm(pts1[:2]-pts2[:2]) # minimal point distance between two nodes in 2D
            nn_dist = np.linalg.norm(pts1[:3]-pts2[:3]) # minimal point distance between two nodes in 3D; equivalent to: nn_dist = np.min(nn_dist)
            distance_pairs[k * i + j, 0] = i
            distance_pairs[k * i + j, 1] = nv
            distance_pairs[k * i + j, 2] = nn_dist #use 3D distance to create distance graph for connectivity analysis
            distance_pairs[k * i + j, 3] = nn_dist2d

    # use 2D distance to filter out far neighbors (3D distance is not suitable here due to strong vertical point occlusion)
    distance_pairs = distance_pairs[distance_pairs[:, -1] < max_distance]
    graph = csr_matrix((distance_pairs[:, -2], (distance_pairs[:, 0], distance_pairs[:, 1])), shape=(n_centroids, n_centroids))
    graph = (graph + graph.T) / 2
    return graph,node_total

def cluster_graph(graph,node_total,target_idx):

    distances = dijkstra(graph, indices=target_idx, return_predecessors=False)#shortest paths from each node to each stem node
    distances = distances.T
    # for each row (node), find the stem node id (column) with the shortest path
    min_dist_idx = np.argmin(distances, axis=1, keepdims=True)
    min_dist = np.take_along_axis(distances, min_dist_idx, axis=1)[:, 0]
    nearest_targets = target_idx[min_dist_idx[:, 0]]#stem node id (column) with the shortest path
    filter_ind = ~np.isinf(min_dist)
    nearest_targets = nearest_targets[filter_ind]#exclude the infinite ones
    nearest_idx = np.where(filter_ind)[0]
    nearest_targets_u,nearest_targets=np.unique(nearest_targets,return_inverse=True)#shuffle the labels in order from 0-N
    label_pred = np.zeros(node_total)-1#assign -1 as default label (assigning 0 will mess up with the node ID starting from 0)
    label_pred[nearest_idx] = nearest_targets

    # label_unq,label_pred=np.unique(label_pred,return_inverse=True)#shuffle the labels in order from 0-N
    return label_pred,len(nearest_targets_u)

def shortestpath3D(points,stemcls,base_loc,min_res=0.06, max_isolated_distance = 0.3, progress_callback=lambda x: None):

    if stemcls is None:
        pcd = points
        stem_idx=None
    else:
        stem_idx = np.where(stemcls>1)[0]
        if len(stem_idx) == 0:
            print("There are no stem points")
            return
        pcd = points[stem_idx]


    dec_idx_uidx, dec_inverse_idx = decimate_pcd(pcd[:, :3], min_res)  # reduce point number first to avoid computation overhead
    pcd_dec = pcd[dec_idx_uidx]
    pcd_dec_min=np.min(pcd_dec[:,:3],axis=0)
    pcd_dec[:,:3]=pcd_dec[:,:3]-pcd_dec_min

    pcd_base_loc=base_loc.copy()
    pcd_base_loc[:, :3]=base_loc[:,:3]-pcd_dec_min

    progress_callback(15)

    #create connectivity graph and separate into connected components
    graph = create_sparse_graph(pcd_dec[:, :3], k=min(len(pcd_dec),10), max_distance=min_res * 3)
    n_comps, conn_labels = connected_components(graph, directed=False, return_labels=True)

    progress_callback(30)

    #find the points nearest to the base locations as the base points
    kdtree = cKDTree(pcd_dec[:,:3])
    distances, indices = kdtree.query(pcd_base_loc[:,:3])
    conn_base_idx=conn_labels[indices] #get the component ID of base points as the base IDs

    #the return_inverse from np.unique function can be used to group the conn_labels into lists (or split the arrays into lists by the unique conn_labels)
    _, comp_inverse_idx, comp_size = np.unique(conn_labels, return_inverse=True, return_counts=True)
    _, comp_idx_groups = npi.group_by(comp_inverse_idx, np.arange(len(comp_inverse_idx)))

    # for each component if there are more than two base points, split the component by bayesian gaussian mixture decomposition (best results among all other binary segmentation methods)
    conn_base_idx_unq,conn_base_idx_inverse,base_per_conn_counts=np.unique(conn_base_idx,return_inverse=True,return_counts=True)
    _, conn_base_idx_groups = npi.group_by(conn_base_idx_inverse, np.arange(len(conn_base_idx_inverse)))

    to_split_idx=np.where(base_per_conn_counts>1)[0]
    conn_idxs_to_split=conn_base_idx_unq[to_split_idx]
    base_per_conn_counts=base_per_conn_counts[to_split_idx].astype(np.int32)

    conn_labels_split=conn_labels
    max_counter=n_comps
    for i,conn_idx_to_split in enumerate(conn_idxs_to_split):
        comp_pts=pcd_dec[comp_idx_groups[conn_idx_to_split],:3]
        bgm = BayesianGaussianMixture(n_components=base_per_conn_counts[i], init_params="k-means++",random_state=42).fit(comp_pts)
        labels = bgm.predict(comp_pts)
        conn_labels_split[comp_idx_groups[conn_idx_to_split]]=labels+max_counter
        max_counter+=base_per_conn_counts[i]

    _, conn_labels, comp_size = np.unique(conn_labels_split, return_inverse=True, return_counts=True)#re-order the component labels from 0-N
    conn_base_idx=conn_labels[indices] #update base IDs with new component IDs of base points

    n_comps=len(comp_size)
    #return_inverse of the np.unique function is my favorite way to restore the connected component ids (unique values of conn_labels)
    # to the original order of conn_labels (or equivalently original order of points in pcd_dec);
    _, comp_inverse_idx, comp_size = np.unique(conn_labels, return_inverse=True, return_counts=True)

    progress_callback(50)

    #created a connectivity graph with pairs of nearest K nodes, their minimal 3D point distance to be the edge weight.
    comp_graph, comp_total = create_node_graph(np.concatenate([pcd_dec[:,:3], conn_labels[:, np.newaxis]], axis=-1), k=10, max_distance=max_isolated_distance)

    progress_callback(70)

    # For each node, find its associated stem node ID with the shortest path among all other stem nodes, and then assign the base ID of this stem node to this node
    seg_pred, seg_total = cluster_graph(comp_graph, n_comps, conn_base_idx)
    # Map IDs from node to point based on the inverse indices
    # (1. from node to decimated point cloud, 2. from decimated to original point cloud)
    all_pred = seg_pred[comp_inverse_idx][dec_inverse_idx].astype(np.int32)

    pcd_pred_labels=np.zeros(len(points))
    if stemcls is None:
        pcd_pred_labels = all_pred
    else:
        # tree1=pcd[all_pred==0]
        # if np.sum(np.max(tree1[:,:2])-np.min(tree1[:,:2]))
        pcd_pred_labels[stem_idx]=all_pred+1

    progress_callback(100)
    return pcd_pred_labels


if __name__ =='__main__':

    import os
    import laspy
    # path_to_las = r"D:\xzx\prj\cc-TreeAIBox-plugin\data\JP10_plot_2cm_test3.las"
    path_to_las = r"D:\xzx\prj\cc-TreeAIBox-plugin\data\RPine_plot1_sep.las"
    # path_to_las = r"..\..\data\2023_NWT-7N-31_REG-V2_SUB-2_SOR-6-3_2.las"
    pcd_basename = os.path.basename(path_to_las)[:-4]
    las = laspy.read(path_to_las)
    pcd=np.transpose([las.x,las.y,las.z,las.stemcls])

    pcd_min=np.min(pcd[:,:3],0)
    pcd[:,:3]=pcd[:,:3]-pcd_min

    min_res=0.06
    max_isolated_distance = 0.3

    stem_ind=pcd[:,-1]==2

    # path_to_base=r"..\..\data\2023_NWT-7N-31_REG-V2_SUB-2_SOR-6-3_2_base.csv"
    # path_to_base=r"D:\xzx\prj\cc-TreeAIBox-plugin\data\JP10_plot_2cm_test3_base.csv"
    # path_to_base=r"D:\xzx\prj\cc-TreeAIBox-plugin\data\TAspen_plot1_sep_treebase.csv"
    path_to_base=r"D:\xzx\prj\cc-TreeAIBox-plugin\data\RPine_plot1_sep_treebase.csv"
    pcd_base=np.loadtxt(path_to_base, delimiter=' ')
    pcd_base=np.unique(pcd_base,axis=0)

    pcd_base=pcd_base-pcd_min

    labels=shortestpath3D(pcd, pcd[:,-1], pcd_base, min_res,max_isolated_distance)

    las.add_extra_dim(laspy.ExtraBytesParams(name="shortestpath3d", type="int32", description="shortestpath3d"))
    # stem_out=np.zeros(len(las.x))
    # stem_out[stem_ind]=labels
    las.shortestpath3d = labels
    las.write(r"C:\Users\ZXI\Downloads\shortestpath3d.laz")
    # las.write(r"C:\Users\trueb\Downloads\shortestpath3d.laz")