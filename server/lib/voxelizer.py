"""
Voxelizer module — converts 3D meshes (.obj) into Minecraft 3D block grids.

Uses trimesh to load and voxelize the mesh.
"""
import os
import logging
import numpy as np
import trimesh

logger = logging.getLogger(__name__)

def voxelize_mesh(file_path: str, max_size: int = 50) -> list[dict]:
    """
    Load a 3D mesh, scale it to max_size, and convert to a flat list of blocks.
    Returns: [{"x": x, "y": y, "z": z, "block": "minecraft:stone"}, ...]
    """
    if not os.path.exists(file_path):
        logger.error(f"[voxelizer] File not found: {file_path}")
        return []

    logger.info(f"[voxelizer] Loading mesh from {file_path}...")
    try:
        # Load the mesh. Turn force='mesh' to merge scenes into one mesh.
        scene = trimesh.load(file_path, force='mesh')
        
        if isinstance(scene, trimesh.Scene):
            # If it's a scene, dump to a single mesh
            if len(scene.geometry) == 0:
                logger.error("[voxelizer] Empty scene loaded.")
                return []
            mesh = trimesh.util.concatenate([geom for geom in scene.geometry.values()])
        else:
            mesh = scene

        # Scale the mesh so its largest dimension is `max_size` blocks
        extents = mesh.extents
        scale_factor = max_size / max(extents)
        
        # Create a scaling matrix
        scale_matrix = trimesh.transformations.scale_matrix(scale_factor)
        mesh.apply_transform(scale_matrix)

        # Move bottom-left back corner to (0, 0, 0)
        bounds_min = mesh.bounds[0]
        translation_matrix = trimesh.transformations.translation_matrix(-bounds_min)
        mesh.apply_transform(translation_matrix)

        bounds = mesh.bounds
        logger.info(f"[voxelizer] Scaled mesh to bounds: {bounds[1]}")

        # Voxelize the mesh
        # pitch=1.0 means each voxel is 1x1x1 (1 block)
        # We try 'subdivide' first as it creates a nice shell for non-watertight AI generated meshes
        logger.info("[voxelizer] Voxelizing mesh (this may take a moment)...")
        try:
            voxels = mesh.voxelized(pitch=1.0, method='subdivide')
        except Exception as e:
            logger.warning(f"[voxelizer] Subdivide failed ({e}), falling back to ray voxelization...")
            voxels = mesh.voxelized(pitch=1.0)
            
        # Optional: fill the inside if it's watertight
        try:
            voxels = voxels.fill()
        # trunk-ignore-next-line(ruff/F401)
        except:
            pass # Ignore if not watertight

        # matrix is a 3D boolean numpy array [x, y, z]
        matrix = voxels.matrix
        logger.info(f"[voxelizer] Voxel matrix shape: {matrix.shape}")

        blocks = []
        
        # Convert textures to vertex/face colors if needed
        if hasattr(mesh.visual, 'to_color'):
            mesh.visual = mesh.visual.to_color()
        
        # Extract the XYZ coordinates of the solid voxels
        points = np.argwhere(matrix)
            
        color_map = {}
        if len(points) > 0 and hasattr(mesh.visual, 'face_colors') and len(mesh.faces) > 0:
            logger.info("[voxelizer] Extracting colors from closest mesh faces...")
            # voxels.points is an array of the actual 3D center points of the solid voxels corresponding to 'points'
            # We map this to the original mesh to find the closest triangle face
            closest, distance, triangle_id = trimesh.proximity.closest_point(mesh, voxels.points)
            
            # The visual face colors 
            face_colors = mesh.visual.face_colors
            for i, pt in enumerate(points):
                tid = triangle_id[i]
                if tid < len(face_colors):
                    r, g, b, a = face_colors[tid]
                    # tuple(pt) is (x, y, z)
                    color_map[tuple(pt)] = [int(r), int(g), int(b)]

        for x in range(matrix.shape[0]):
            for y in range(matrix.shape[1]):
                for z in range(matrix.shape[2]):
                    if matrix[x, y, z]:
                        voxel_color = color_map.get((x, y, z), [125, 125, 125])
                        blocks.append({
                            "x": x,
                            "y": y,
                            "z": z,
                            "block": "minecraft:stone",
                            "color": voxel_color
                        })
                        
        logger.info(f"[voxelizer] Generated {len(blocks)} solid blocks.")
        return blocks

    except Exception as e:
        logger.error(f"[voxelizer] Failed to voxelize: {e}", exc_info=True)
        return []

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1:
        voxelize_mesh(sys.argv[1], 30)
