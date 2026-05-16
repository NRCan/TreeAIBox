import math
import numpy as np
import numpy_indexed as npi
import numpy_groupies as npg

from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from scipy import interpolate
from scipy.signal import medfilt

# from sklearn.cluster import mean_shift
import cut_pursuit_py
from circle_fit import riemannSWFLa


import xml.etree.ElementTree as ET
from xml.dom import minidom


# NEED TO IMPROVE:
# The progress bar value is better to be updated with a callback function
# Need to visualize the meshes directly, instead of saving and loading the meshes.
# Current algorithm works poorly on the branchy and fat trees (tropical trees); But this can be improved without much difficulty.

def saveTreeToXML(tree_list,attribute_list,filename):
    root = ET.Element("tree")
    branches = {}
    branch_id_counter = 1
    
    # Filter out branches with insufficient nodes
    valid_branches = []
    for branch, attrs in zip(tree_list, attribute_list):
        if len(branch) < 1 or len(attrs) < 1:
            print(f"[QSM Warning] Skipping invalid branch in XML export")
            continue
        valid_branches.append((branch, attrs))
        branches[branch[0]] = (branch, attrs)
    
    if not valid_branches:
        print(f"[QSM Warning] No valid branches to save to XML")
        # Create empty tree XML
        xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
        with open(filename, "w", encoding="utf-8") as file:
            file.write(xml_str)
        return

    def create_branch(parent_node, nodes, attrs, level, prev_node_in_parent):
        nonlocal branch_id_counter
        branch = ET.SubElement(root, "branch", id=str(branch_id_counter), parent_node=str(parent_node), level=str(level))
        branch_id_counter += 1
        prev_node = prev_node_in_parent
        # Add the parent node to the branch
        if parent_node != -1:
            parent_branch_nodes, parent_branch_attrs = branches[parent_node]
            parent_index = parent_branch_nodes.index(parent_node)
            parent_attr = parent_branch_attrs[parent_index]
            add_node(branch, parent_node, prev_node, level, parent_attr)
            prev_node = parent_node

        for node, attr in zip(nodes, attrs):
            node_elem = add_node(branch, node, prev_node, level, attr)
            if node in branches and branches[node][0] != nodes:
                create_branch(node, branches[node][0][1:], branches[node][1][1:], level + 1, prev_node)
                # Move the created sub-branch inside this node
                sub_branch_elem = root.find(f".//branch[@parent_node='{node}']")
                if sub_branch_elem is not None:
                    root.remove(sub_branch_elem)
                    node_elem.append(sub_branch_elem)
            prev_node = node

    def add_node(branch, node, prev_node, level, attr):
        return ET.SubElement(branch, "node", {
            "id": str(node),
            "prev_node": str(prev_node),
            "level": str(level),
            "x": f"{attr[0]:.6f}",
            "y": f"{attr[1]:.6f}",
            "z": f"{attr[2]:.6f}",
            "radius": f"{attr[3]:.6f}"
        })

    if valid_branches:
        create_branch(-1, valid_branches[0][0], valid_branches[0][1], 1, -1)
    
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    with open(filename, "w", encoding="utf-8") as file:
        file.write(xml_str)


def removeNanVerticesAndAdjustFaces(vertices, faces):
    vertices = np.array(vertices)
    faces = np.array(faces)
    valid_indices = ~np.isnan(vertices).any(axis=1)
    index_map = np.cumsum(valid_indices) - 1
    filtered_vertices = vertices[valid_indices]
    adjusted_faces = index_map[faces]
    valid_faces = adjusted_faces[~(adjusted_faces < 0).any(axis=1)]
    return filtered_vertices.tolist(), valid_faces.tolist()

def saveTreeToObj(tree_centroid_radius,fname, interval_distance=0.05, num_sides=16):
    all_vertices = []
    all_faces = []
    vertex_offset = 0
    for curve_nodes in tree_centroid_radius:
        # Skip branches with insufficient nodes (need at least 2 for tube creation)
        if len(curve_nodes) < 2:
            print(f"[QSM Warning] Skipping branch with only {len(curve_nodes)} node(s)")
            continue
            
        if len(curve_nodes) <= 3:
            vertices, faces = createLineTube(curve_nodes, interval_distance, num_sides)
        else:
            vertices, faces = createBezierTube(curve_nodes, interval_distance, num_sides)
        # Remove NaN vertices and adjust faces
        vertices, faces = removeNanVerticesAndAdjustFaces(vertices, faces)
        # Adjust face indices based on the current vertex offset
        adjusted_faces = [(f[0] + vertex_offset, f[1] + vertex_offset,
                           f[2] + vertex_offset, f[3] + vertex_offset) for f in faces]
        all_vertices.extend(vertices)
        all_faces.extend(adjusted_faces)
        vertex_offset += len(vertices)
    # Export to OBJ
    with open(fname, 'w') as f:
        for vertex in all_vertices:
            f.write(f"v {vertex[0]} {vertex[1]} {vertex[2]}\n")
        for face in all_faces:
            f.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1} {face[3] + 1}\n")

def constrain_radii(radii, max_factor=1.1):
    constrained_radii = [radii[0]]
    for r in radii[1:]:
        max_allowed = constrained_radii[-1] * max_factor
        constrained_radii.append(min(r, max_allowed))
    return np.array(constrained_radii)

def createLineTube(nodes, interval_distance=0.1, num_sides=16):
    coords = np.array([node[:3] for node in nodes])
    radii = np.array([node[3] for node in nodes])

    # Extend the start and end points
    start_extension = coords[0] - 0.5 * (coords[1] - coords[0])
    end_extension = coords[-1] + 0.5 * (coords[-1] - coords[-2])

    extended_coords = np.vstack((start_extension, coords, end_extension))

    # Extend radii (using the same radius for extended points)
    extended_radii = np.hstack((radii[0], radii, radii[-1]))

    # Calculate total length of the extended path
    path_length = np.sum(np.linalg.norm(np.diff(extended_coords, axis=0), axis=1))

    # Calculate number of segments based on interval distance
    num_segments = max(2, int(path_length / interval_distance))

    # Generate points along the extended line
    t = np.linspace(0, 1, num_segments)
    points = np.array([np.interp(t, np.linspace(0, 1, len(extended_coords)), extended_coords[:, i]) for i in range(3)]).T

    # Interpolate radii along the extended line
    interpolated_radii = np.interp(t, np.linspace(0, 1, len(extended_radii)), extended_radii)

    return generateTubeMesh(points, interpolated_radii, num_sides)


def createBezierTube(nodes, interval_distance=0.1, num_sides=16):
    coords = np.array([node[:3] for node in nodes])
    radii = np.array([node[3] for node in nodes])

    # Extend the start and end points
    start_extension = coords[0] - 0.5 * (coords[1] - coords[0])
    end_extension = coords[-1] + 0.5 * (coords[-1] - coords[-2])

    extended_coords = np.vstack((start_extension, coords, end_extension))

    # Extend radii (using the same radius for extended points)
    extended_radii = np.hstack((radii[0], radii, radii[-1]))

    # Generate initial Bezier curve with a reasonable number of points
    initial_points = 100
    t_initial = np.linspace(0, 1, initial_points)
    tck, u = interpolate.splprep(extended_coords.T, s=0)
    points_initial = np.array(interpolate.splev(t_initial, tck)).T

    # Calculate total length of the path
    path_length = np.sum(np.linalg.norm(np.diff(points_initial, axis=0), axis=1))

    # Calculate number of segments based on interval distance
    num_segments = max(2, int(path_length / interval_distance))

    # Generate final points
    t = np.linspace(0, 1, num_segments)
    points = np.array(interpolate.splev(t, tck)).T

    # Interpolate radii along the curve
    radii_interpolator = interpolate.interp1d(np.linspace(0, 1, len(extended_radii)), extended_radii)
    interpolated_radii = radii_interpolator(t)

    return generateTubeMesh(points, interpolated_radii, num_sides)

def generateTubeMesh(points, radii, num_sides):#there might be bugs in this function
    vertices = []
    faces = []
    num_segments = len(points)
    for i in range(num_segments):
        if i < num_segments - 1:
            direction = points[i + 1] - points[i]
        else:
            direction = points[i] - points[i - 1]
        # Create orthonormal basis
        z_axis = direction / np.linalg.norm(direction)
        x_axis = np.array([1, 0, 0])
        if np.allclose(z_axis, x_axis):
            x_axis = np.array([0, 1, 0])
        y_axis = np.cross(z_axis, x_axis)
        x_axis = np.cross(y_axis, z_axis)
        x_axis /= np.linalg.norm(x_axis)
        y_axis /= np.linalg.norm(y_axis)
        # Generate circle points
        for j in range(num_sides):
            angle = 2 * math.pi * j / num_sides
            x = radii[i] * math.cos(angle)
            y = radii[i] * math.sin(angle)
            point = points[i] + x * x_axis + y * y_axis
            vertices.append(point)
        # Generate faces
        if i < num_segments - 1:
            for j in range(num_sides):
                j_next = (j + 1) % num_sides
                v1 = i * num_sides + j
                v2 = i * num_sides + j_next
                v3 = (i + 1) * num_sides + j_next
                v4 = (i + 1) * num_sides + j
                faces.append((v1, v2, v3, v4))
    return vertices, faces

def findNearestTarget(graph,target_indices,max_graph_distance=np.inf):
    # Compute the shortest paths to all targets
    distances,predecessors = dijkstra(graph, directed=False,indices=target_indices, return_predecessors=True,limit=max_graph_distance)
    distances=distances.T
    min_dist_idx = np.argmin(distances, axis=1,keepdims=True)
    nearest_distances = np.take_along_axis(distances, min_dist_idx, axis=1)[:,0]
    nearest_targets = target_indices[min_dist_idx[:,0]]
    filter_ind = np.isinf(nearest_distances)
    nearest_targets = nearest_targets[~filter_ind]
    nearest_idx=np.where(~filter_ind)[0]
    nearest_distances=nearest_distances[~filter_ind]
    return nearest_targets,nearest_idx,nearest_distances,predecessors

def getConnectivity(points,k=6,max_distance=0.03):
    kdtree = cKDTree(points[:,:3])
    distances, indices = kdtree.query(points[:,:3], k=k + 1, distance_upper_bound=max_distance,)
    distances = distances[:, 1:].ravel()
    indices = indices[:, 1:]
    row_idx = np.repeat(np.arange(len(points)), k)
    col_idx = indices.ravel()
    valid = np.isfinite(distances)
    row_idx = row_idx[valid]
    col_idx = col_idx[valid]

    joint_ind=(points[row_idx,-1]!=points[col_idx,-1])#this is to find the boundary between two connected segs because the labels between two segs won't match
    joint_row_idx=row_idx[joint_ind]
    joint_col_idx=col_idx[joint_ind]

    seg_id_pairs=np.unique(np.transpose([points[joint_row_idx, -1],points[joint_col_idx, -1]]), axis=0)
    return seg_id_pairs

def getPointwiseClusterDistance(pts,segs_centroids,segs_centroids_stem,max_connectivity_search_k,max_connectivity_search_distance,occlusion_distance_cutoff,nn_centroids_k=6,weight_min_dist=0.03):
    kdtree = cKDTree(segs_centroids[:,:3])
    centroids_nn_distances, centroids_nn_indices = kdtree.query(segs_centroids[:,:3], k=nn_centroids_k + 1)
    #choose to calculate the knn neighbors of each point, and their label difference could be used to update the connectivity matrix#future: could reduce the time by ignoring paris between stem pts
    seg_id_pairs=getConnectivity(pts, k=max_connectivity_search_k, max_distance=max_connectivity_search_distance)#mutually connected or not
    seg_id_pairs_set = set(map(tuple, seg_id_pairs))
    seg_id_pairs_set.update(set(map(tuple, seg_id_pairs[:, ::-1])))  # Add reverse pairs

    rows0 = np.repeat(np.arange(len(segs_centroids)), nn_centroids_k)
    cols0 = centroids_nn_indices[:, 1:].ravel()
    distances0 = centroids_nn_distances[:, 1:].ravel()

    #remove those mutual connection between stem nodes, keeping only branch nodes and between branch and stem nodes
    non_stem_ind=~np.all(np.transpose([segs_centroids_stem[rows0]>0,segs_centroids_stem[cols0]>0]),axis=1)
    rows=rows0[non_stem_ind]
    cols=cols0[non_stem_ind]
    distances=distances0[non_stem_ind]
    weights=distances

    n_centroids=len(segs_centroids)
    if_connected = np.array([(r,c) in seg_id_pairs_set for r,c in zip(rows,cols)])
    weights[if_connected]=weight_min_dist*weight_min_dist*distances[if_connected]*distances[if_connected] #To ensure the connection between serveral nodes won't skip the nearest node. In an obtuse triangle, the sum of two squared side lengths is larger than the third side

    weights[weights>occlusion_distance_cutoff]=np.inf
    graph = csr_matrix((weights, (rows, cols)), shape=(n_centroids, n_centroids))
    return graph,rows0,cols0,distances0,seg_id_pairs_set

def updatePointwiseClusterDistance(rows0,cols0,distances0,seg_id_pairs_set,segs_centroids_conn_stemlabels,occlusion_distance_cutoff=0.4,weight_min_dist=0.03):
    n_centroids=len(segs_centroids_conn_stemlabels)
    #remove those mutual connection between stem nodes
    non_stem_ind=~np.all(np.transpose([segs_centroids_conn_stemlabels[rows0]>0,segs_centroids_conn_stemlabels[cols0]>0]),axis=1)
    rows=rows0[non_stem_ind]
    cols=cols0[non_stem_ind]
    distances=distances0[non_stem_ind]
    weights=distances
    if_connected = np.array([(r,c) in seg_id_pairs_set for r,c in zip(rows,cols)])
    weights[if_connected]=weight_min_dist*weight_min_dist*distances[if_connected]*distances[if_connected] #To ensure the connection between serveral nodes won't skip the nearest node. In an obtuse triangle, the sum of two squared side lengths is larger than the third side
    weights[weights>occlusion_distance_cutoff]=np.inf
    graph = csr_matrix((weights, (rows, cols)), shape=(n_centroids, n_centroids))
    return graph
def branchSegmentation(branch_pts,K=5, reg_strength=1.0,resolution=0.0):

    if resolution>0:
        xyz_min = np.min(branch_pts[:, :3], axis=0)
        xyz_max = np.max(branch_pts[:, :3], axis=0)

        block_shape = np.floor((xyz_max[:3] - xyz_min[:3]) / resolution).astype(np.int32) + 1
        block_shape = block_shape[[1, 0, 2]]

        block_x = xyz_max[1] - branch_pts[:, 1]
        block_y = branch_pts[:, 0] - xyz_min[0]
        block_z = branch_pts[:, 2] - xyz_min[2]

        block_ijk = np.floor(np.concatenate([block_x[:, np.newaxis], block_y[:, np.newaxis], block_z[:, np.newaxis]], axis=1) / resolution).astype(np.int32)
        block_idx = np.ravel_multi_index((np.transpose(block_ijk)).astype(np.int32), block_shape)
        block_idx_u, block_idx_uidx, block_inverse_idx = np.unique(block_idx, return_index=True, return_inverse=True)

        pts_dec = branch_pts[block_idx_uidx]
        pts_dec=pts_dec[:,:3]
    else:
        pts_dec=branch_pts[:,:3]



    # cluster_centers, labels = mean_shift(pts_dec[:,:3], bandwidth=bandwidth,bin_seeding=True)

    kdtree = cKDTree(pts_dec)
    _, nn_idx = kdtree.query(pts_dec, k=K+1)

    # Prepare graph structure
    indices = nn_idx[:, 1:]  # exclude self
    n_nodes = len(pts_dec)

    # Create edge lists
    eu = np.repeat(np.arange(n_nodes), K)
    ev = indices.ravel()

    # Edge weights
    edge_weights = np.ones_like(eu, dtype=np.float32)*reg_strength

    # Perform cut pursuit
    labels = cut_pursuit_py.perform_cut_pursuit(
        reg_strength=reg_strength,  # Regularization strength
        D=3,  # Dimension of points
        pc_vec=pts_dec.astype(np.float32),  # Point cloud
        edge_weights=edge_weights,
        Eu=eu.astype(np.uint32),
        Ev=ev.astype(np.uint32),
        verbose=True
    )
    if resolution>0:
        return labels[block_inverse_idx],len(np.unique(labels))
    else:
        return labels, len(np.unique(labels))

def movingAverage(x, w):
    return np.convolve(x, np.ones(w), 'valid') / w

def findStems(pts,segs_centroids,segs_centroids_stem_labels,nn_centroids_k=5,weight_min_dist=0.05):#pts[x,y,z,stemcls[stem:1],init_segs]
    stempts=pts[pts[:,-2]>0]
    stem_labels_idx=np.where(segs_centroids_stem_labels>0)[0]
    segs_centroids_stem=segs_centroids[stem_labels_idx]

    kdtree = cKDTree(segs_centroids_stem[:, :3])
    centroids_nn_distances, centroids_nn_indices = kdtree.query(segs_centroids_stem[:, :3], k=nn_centroids_k + 1)
    # choose to calculate the knn neighbors of each point, and their label difference could be used to update the connectivity matrix#future: could reduce the time by ignoring paris between stem pts
    seg_id_pairs = getConnectivity(stempts, k=nn_centroids_k)  # mutually connected or not
    seg_id_pairs_set = set(map(tuple, seg_id_pairs))
    seg_id_pairs_set.update(set(map(tuple, seg_id_pairs[:, ::-1])))  # Add reverse pairs

    rows = np.repeat(np.arange(len(segs_centroids_stem)), nn_centroids_k)
    cols = centroids_nn_indices[:, 1:].ravel()
    distances = centroids_nn_distances[:, 1:].ravel()

    weights = np.full(len(distances),np.inf)

    n_centroids = len(segs_centroids_stem)
    if_connected = np.array([(r, c) in seg_id_pairs_set for r, c in zip(rows, cols)])
    weights[if_connected] = weight_min_dist * weight_min_dist * distances[if_connected] * distances[if_connected]  # To ensure the connection between serveral nodes won't skip the nearest node. In an obtuse triangle, the sum of two squared side lengths is larger than the third side

    graph = csr_matrix((weights, (rows, cols)), shape=(n_centroids, n_centroids))

    start_index=np.argmin(segs_centroids_stem[:,2])
    distances,predecessors = dijkstra(graph, directed=False,indices=start_index, return_predecessors=True)
    connected_centroids_idx=np.where(~np.isinf(distances))[0]
    end_index=connected_centroids_idx[np.argmax(distances[connected_centroids_idx])]
    stem_path = [end_index]
    stem_path.extend(predecessors[current] for current in stem_path if current >= 0)
    stem_path = stem_path[:-1]
    stem_path=stem_path[::-1]#from bottom to top

    segs_centroids_stem_labels=np.zeros(len(segs_centroids))
    segs_centroids_stem_labels[stem_labels_idx[stem_path]]=1

    return stem_labels_idx[stem_path],segs_centroids_stem_labels


def initSegmentation(pts,K_stem=5,reg_strength_stem=1.0,K_branch=10,reg_strength_branch=1.0,progress_callback=lambda x: None):
    progress_callback(0)

    init_segs = np.zeros(len(pts),dtype=np.int32)
    stemcls=pts[:,-1]
    stem_pts_ind = (stemcls>1.0)
    stem_pts = pts[stem_pts_ind,:]
    progress_callback(10)

    # init_segs[stem_pts_ind], n_stem_segs=branchSegmentation(stem_pts, stem_spacing)
    init_segs[stem_pts_ind], n_stem_segs=branchSegmentation(stem_pts,K=K_stem, reg_strength=reg_strength_stem)

    # branch_segs_labels,n_branch_segs=branchSegmentation(pts[~stem_pts_ind], bandwidth=branch_bandwidth)
    branch_pts=pts[~stem_pts_ind]
    branch_segs_labels,n_branch_segs=branchSegmentation(branch_pts,K=K_branch, reg_strength=reg_strength_branch)
    init_segs[~stem_pts_ind] = branch_segs_labels+n_stem_segs

    progress_callback(100)
    return init_segs.astype(np.int32)

def refineBranchHead(tree,segs_centroids,max_distance=0.3):
    branch_head_segment=np.array([path[:3] for path in tree if len(path)>2])
    branch_path_idx=np.array([i for i,path in enumerate(tree) if len(path)>2])
    branch_head_pts=segs_centroids[branch_head_segment[:,0]][:, :3]
    branch_head_previous_pts=segs_centroids[branch_head_segment[:, 1]][:, :3]
    branch_head_previous_previous_pts=segs_centroids[branch_head_segment[:, 2]][:, :3]
    branch_head_previous_dir=branch_head_previous_previous_pts-branch_head_previous_pts
    branch_head_previous_dir=branch_head_previous_dir/np.linalg.norm(branch_head_previous_dir, axis=-1)[:, np.newaxis]

    kdtree = cKDTree(branch_head_pts)
    branch_head_nn_distances, branch_head_nn_indices = kdtree.query(branch_head_previous_pts, k=4,distance_upper_bound=max_distance)
    for i in range(len(branch_head_previous_pts)):
        valid_i=np.where(np.all([branch_head_nn_distances[i, :]>0,(~np.isinf(branch_head_nn_distances[i, :]))],axis=0))[0]#find head from the second: not too far and not itself
        if len(valid_i)>0:
            branch_head_vec=(branch_head_previous_pts[i]-branch_head_pts[branch_head_nn_indices[i, valid_i]])
            branch_head_dir=branch_head_vec/np.linalg.norm(branch_head_vec, axis=-1)[:, np.newaxis]
            if len(branch_head_dir)>1:
                branch_head_nn_idx=np.argmin(np.arccos(np.dot(branch_head_dir,branch_head_previous_dir[i])))
            else:
                branch_head_nn_idx=0
            tree[branch_path_idx[i]][0]=branch_head_segment[branch_head_nn_indices[i,valid_i[branch_head_nn_idx]],0]
    return tree

def recreateTreePath(stems_idx,graph,n_segs_centroids,max_graph_distance,tree=None,init_seg_id=2,segs_labels=None):# this needs to be improved
    # Find nearest targets
    nearest_targets, nearest_idxs,nearest_distances,predecessors = findNearestTarget(graph, stems_idx, max_graph_distance)
    target_position = {t: i for i, t in enumerate(stems_idx)}
    used_nodes = set(stems_idx)  # Initialize with target nodes
    if tree is None:
        tree = [stems_idx.tolist()]  # tree: stem comes first; bottom node as the first node
    if segs_labels is None:
        segs_labels = np.zeros(n_segs_centroids)
        segs_labels[stems_idx]=1

    # Sort paths by distance (longest first)
    sorted_indices = np.argsort(nearest_distances)[::-1]
    seg_id = init_seg_id
    for idx in sorted_indices:
        path = []
        current = nearest_idxs[idx]
        target = nearest_targets[idx]
        target_pos = target_position[target]

        while current not in used_nodes:
            path.append(current)
            used_nodes.add(current)
            current = predecessors[target_pos, current]

        if path:
            path.append(current)  # Add the connecting node (either a used node or the target)
            # Future: if the path curvature is too twisted, just cut the path
            tree.append(path[::-1])  # Reverse the path for correct order
            segs_labels[path[::-1][1:]] = seg_id  # from parent branch to branch end
            seg_id += 1
            # # smooth nodes
            # for k in range(3):
            #     segs_centroids[path[::-1],k] = movingAverage(segs_centroids[path[::-1],k],smooth_ma_k)
    return tree,segs_labels,seg_id-1

def cleanTree(tree,segs_centroids_counts,segs_labels,min_pts=5):
    keep_idx=[]
    for i,path in enumerate(tree):
        if len(path)<3:
            if segs_centroids_counts[path[-1]] <= min_pts:
                segs_labels[path[1:]]=0.0
                continue
        keep_idx.append(i)
    tree=[tree[idx] for idx in keep_idx]
    return tree,segs_labels

def calculateRadius(pts,tree,segs_centroids,min_r=0.04):# this needs to be improved
    _, segs_centroids_group = npi.group_by(pts[:, -1].astype(np.int32), np.arange(len(pts[:, -1])))
    tree_centroid_radius=[]
    for path in tree:
        path_centroid_radius=[]
        segs_centroid_vec=segs_centroids[path[1:]]-segs_centroids[path[:-1]]
        segs_centroid_dir=segs_centroid_vec/np.linalg.norm(segs_centroid_vec, axis=-1)[:, np.newaxis]
        for i,node in enumerate(path[1:]):
            if len(segs_centroids_group[node]) > 4:
                try:
                    #project to the horizontal plane and circle fitting
                    segs_vec = pts[segs_centroids_group[node],:3]-segs_centroids[node,:3]
                    segs_prj = np.dot(segs_vec, segs_centroid_dir[i,:3])
                    segs_prj_2d=pts[segs_centroids_group[node],:2] - np.outer(segs_prj, segs_centroid_dir[i,:3])[:, :2]
                    
                    # Check for NaN or inf values before circle fitting
                    if not np.all(np.isfinite(segs_prj_2d)):
                        # Fallback to min_r if projected data is invalid
                        path_centroid_radius.append(np.array([segs_centroids[node,0],segs_centroids[node,1],segs_centroids[node,2],min_r]))
                        continue
                    
                    r0=np.median(np.sqrt(np.sum(np.power(segs_prj_2d-np.mean(segs_prj_2d,0),2),axis=1)))
                    
                    # Validate r0 before circle fitting
                    if not np.isfinite(r0) or r0 < 1e-6:
                        # Points are too close together, use min_r
                        path_centroid_radius.append(np.array([segs_centroids[node,0],segs_centroids[node,1],segs_centroids[node,2],min_r]))
                        continue
                    
                    xc, yc, r, sigma = riemannSWFLa(segs_prj_2d)
                    
                    # Check if circle fitting produced valid results
                    if not np.isfinite(r) or not np.isfinite(sigma) or r < 1e-6:
                        # Circle fitting failed, use r0 as fallback
                        path_centroid_radius.append(np.array([segs_centroids[node,0],segs_centroids[node,1],segs_centroids[node,2],r0]))
                    elif sigma/r>0.3:#only fit circles when the branches or stems are large enough
                        path_centroid_radius.append(np.array([segs_centroids[node,0],segs_centroids[node,1],segs_centroids[node,2],r0]))
                    else:
                        # path_centroid_radius.append(np.array([xc,yc,segs_centroids[node,2],np.minimum(r,r0*1.2)]))
                        path_centroid_radius.append(np.array([segs_centroids[node,0],segs_centroids[node,1],segs_centroids[node,2],np.minimum(r,r0*1.2)]))
                except Exception as e:
                    # Any error in circle fitting, use min_r as safe fallback
                    print(f"[QSM Warning] Circle fitting failed for node {node}: {e}, using min_r={min_r}")
                    path_centroid_radius.append(np.array([segs_centroids[node,0],segs_centroids[node,1],segs_centroids[node,2],min_r]))
            else:
                path_centroid_radius.append(np.array([segs_centroids[node,0],segs_centroids[node,1],segs_centroids[node,2],min_r]))

        if len(path_centroid_radius)>3:
            # Apply moving median filter to the radii
            radii = np.array([node[3] for node in path_centroid_radius])
            filtered_radii = medfilt(radii, kernel_size=3)
            for i, filtered_radius in enumerate(filtered_radii):
                path_centroid_radius[i][3] = filtered_radius

        # Add the first node with appropriate radius
        if len(path_centroid_radius) > 0:
            # Use the radius from the first calculated node
            first_node_radius = path_centroid_radius[0][-1]
        else:
            # Path has only 1 node or all nodes failed to calculate radius, use min_r
            print(f"[QSM Warning] Path with {len(path)} nodes has no calculated radii, using min_r={min_r}")
            first_node_radius = min_r
        
        path_centroid_radius.insert(0,np.array([segs_centroids[path[0],0],segs_centroids[path[0],1],segs_centroids[path[0],2],first_node_radius]))
        tree_centroid_radius.append(path_centroid_radius)
    return tree_centroid_radius

def applyQSM(pts,k_neighbors=6,max_graph_distance=40, max_connectivity_search_distance=0.03, occlusion_distance_cutoff=0.4,smooth_ma_k=3,progress_callback=lambda x: None,wd=None):#pts[x,y,z,stemcls[stem:1],init_segs]
    progress_callback(0)


    segs_centroids = npg.aggregate(pts[:, -1].astype(np.int32), pts[:, :3], axis=0, func=np.mean)#pts[-1] is init_segs
    segs_centroids_counts = npg.aggregate(pts[:, -1].astype(np.int32), 1)#pts[-1] is init_segs
    segs_centroids_stem_labels = npg.aggregate(pts[:, -1].astype(np.int32), pts[:, -2], axis=0, func=np.max)#pts[-1] is init_segs
    _, segs_centroids_inverse_idx = np.unique(pts[:, -1].astype(np.int32), return_inverse=True)

    # find stems by the longest among the shortest pathes to the bottom point
    stems_idx,segs_centroids_stem_labels=findStems(pts,segs_centroids,segs_centroids_stem_labels)
    graph, rows0, cols0, distances0, seg_id_pairs_set = getPointwiseClusterDistance(pts, segs_centroids, segs_centroids_stem_labels, max_connectivity_search_k=k_neighbors, max_connectivity_search_distance=max_connectivity_search_distance, occlusion_distance_cutoff=occlusion_distance_cutoff*0.5,nn_centroids_k=k_neighbors)

    progress_callback(40)


    n_segs_centroids=len(segs_centroids)
    tree,segs_labels,n_segs=recreateTreePath(stems_idx, graph, n_segs_centroids,max_graph_distance)

    progress_callback(60)


    stem_new_ind=segs_labels>0
    stem_new_idx=np.where(stem_new_ind)[0]

    # repeat the shortest path algorithm to the "less connected" branches
    graph=updatePointwiseClusterDistance(rows0, cols0, distances0, seg_id_pairs_set, stem_new_ind, occlusion_distance_cutoff=occlusion_distance_cutoff,weight_min_dist=0.03)
    tree, segs_labels,n_segs = recreateTreePath(stem_new_idx, graph,n_segs_centroids, max_graph_distance,tree,init_seg_id=n_segs+1,segs_labels=segs_labels)

    progress_callback(70)

    tree=refineBranchHead(tree,segs_centroids,max_distance=occlusion_distance_cutoff)
    tree,segs_labels=cleanTree(tree,segs_centroids_counts,segs_labels)
    tree_centroid_radius=calculateRadius(pts,tree,segs_centroids)
    segs_labels=segs_labels[segs_centroids_inverse_idx].astype(np.int32)

    progress_callback(80)
    return tree, segs_centroids,segs_labels,tree_centroid_radius

if __name__ == '__main__':
    # path_to_las = r"F:\prj\CC2\comp\test_data\branch\P5T1_clean.las"
    path_to_las = r"F:\prj\CC2\comp\cc-TreeAIBox-plugin\data\GUY05_000_stemcls_ref_woodcls2.laz"
    import os
    import laspy
    pcd_basename = os.path.basename(path_to_las)[:-4]
    las = laspy.read(path_to_las)

    columns = np.transpose([las.x, las.y, las.z,las.stemcls])
    columns=columns[las.branchcls>1]
    columns[:,:3]=columns[:,:3]-np.min(columns[:,:3],axis=0)
    init_segs_labels = initSegmentation(columns[:,:4], 20, 5.0, 3, 0.01)
    init_segs_labels0=np.zeros(len(las.x))
    init_segs_labels0[las.branchcls>1]=init_segs_labels
    las.add_extra_dim(laspy.ExtraBytesParams(name="init_segs2", type="int32", description="Predicted wood segs"))
    las.init_segs2 = init_segs_labels0
    las.write("tmp_woodsegs.laz")

    # columns = np.transpose([las.x, las.y, las.z,las.stemcls,las.init_segs])
    # columns=columns[las.branchcls>1.0]
    # # columns[:,-2]=columns[:,-2]-np.min(columns[:,-2])
    # tree, segs_centroids,segs_labels,tree_centroid_radius=applyQSM(columns)
    # saveTreeToObj(tree_centroid_radius, "tmp.obj")
    # xml_output = saveTreeToXML(tree,tree_centroid_radius,"tmp.xml")
