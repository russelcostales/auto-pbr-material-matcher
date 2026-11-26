bl_info = {
    'name': 'Auto PBR Material',
    'version': (1, 0, 0),
    'blender': (4, 2, 0),
    'location': 'View3D > Sidebar > Auto PBR Material',
    'category': 'Material',
}

import bpy
from pathlib import Path
import re

# Match suffixes without regard to case or separators.
ALIASES = {
    'color': ('BaseColor', 'BaseColorMap', 'ColorMap', 'Color', 'Albedo', 'AlbedoMap', 'Diffuse', 'DiffuseMap'),
    'roughness': ('Roughness', 'RoughnessMap'),
    'metallic': ('Metallic', 'MetallicMap', 'Metalness', 'MetalnessMap', 'MetalMap'),
    'normal': ('Normal', 'NormalMap', 'NormalOpenGL', 'NormalGL', 'NormalDirectX', 'NormalDX', 'NormalMapOpenGL', 'NormalMapDirectX'),
    'height': ('Height', 'HeightMap', 'Displacement', 'DisplacementMap'),
    'ao': ('AO', 'AOMap', 'AmbientOcclusion', 'AmbientOcclusionMap'),
    'emission': ('Emissive', 'EmissiveMap', 'Emission', 'EmissionMap'),
    'opacity': ('Opacity', 'OpacityMap', 'Alpha', 'AlphaMap'),
}
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff', '.exr', '.bmp', '.webp'}


def normalize(value):
    return re.sub(r'[ _-]+', '', value).casefold()


def index_textures(folder):
    result = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        for match in re.finditer(r'[_ -]', path.stem):
            prefix = path.stem[:match.start()]
            suffix = normalize(path.stem[match.end():])
            kind = next((k for k, names in ALIASES.items()
                         if suffix in {normalize(n) for n in names}), None)
            if kind:
                result.setdefault(prefix.casefold(), {}).setdefault(kind, []).append((path, suffix))
                break
    return result


def find_textures(obj, index):
    # Prefer object name; fall back to one uniquely matching material name.
    matches = index.get(obj.name.casefold())
    if matches is None:
        names = {s.material.name.casefold() for s in obj.material_slots if s.material}
        candidates = [index[n] for n in names if n in index]
        if len(candidates) != 1:
            return None, 'ambiguous material names' if candidates else 'no matching textures'
        matches = candidates[0]
    if any(len(files) != 1 for files in matches.values()):
        return None, 'duplicate texture maps'
    return {kind: files[0] for kind, files in matches.items()}, ''


def load_image(path, color):
    space = 'sRGB' if color else 'Non-Color'
    # Avoid changing color space on images already used elsewhere.
    for img in bpy.data.images:
        if img.source == 'FILE' and img.colorspace_settings.name == space:
            if Path(bpy.path.abspath(img.filepath)).resolve() == path.resolve():
                return img
    img = bpy.data.images.load(str(path), check_existing=False)
    img.colorspace_settings.name = space
    return img


def build_material(mat, maps, directx_default):
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    nodes, links = tree.nodes, tree.links
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (350, 300)
    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = (700, 300)
    links.new(shader.outputs['BSDF'], out.inputs['Surface'])
    uv = nodes.new('ShaderNodeTexCoord')
    uv.location = (-1100, 300)
    textures = {}
    for i, (kind, (path, suffix)) in enumerate(maps.items()):
        tex = nodes.new('ShaderNodeTexImage')
        tex.label = kind.title()
        tex.image = load_image(path, kind in {'color', 'emission'})
        tex.location = (-850, 300 - i * 300)
        links.new(uv.outputs['UV'], tex.inputs['Vector'])
        textures[kind] = tex.outputs['Color']

    for kind, socket in {'color': 'Base Color', 'roughness': 'Roughness',
                         'metallic': 'Metallic', 'emission': 'Emission Color',
                         'opacity': 'Alpha'}.items():
        if kind in textures:
            links.new(textures[kind], shader.inputs[socket])
    if 'emission' in textures:
        shader.inputs['Emission Strength'].default_value = 1.0
    if 'ao' in textures:
        # Principled has no AO socket. Multiply with base color.
        mix = nodes.new('ShaderNodeMixRGB')
        mix.blend_type = 'MULTIPLY'
        mix.inputs[0].default_value = 1.0
        mix.inputs[1].default_value = (0.8, 0.8, 0.8, 1)
        mix.location = (-250, 500)
        if 'color' in textures:
            links.new(textures['color'], mix.inputs[1])
        links.new(textures['ao'], mix.inputs[2])
        links.new(mix.outputs[0], shader.inputs['Base Color'])
    normal_output = None
    if 'normal' in textures:
        normal_color = textures['normal']
        suffix = maps['normal'][1]
        directx = ('directx' in suffix or suffix.endswith('dx') or
                   ('opengl' not in suffix and not suffix.endswith('gl') and directx_default))
        if directx:
            sep = nodes.new('ShaderNodeSeparateColor')
            sep.location = (-570, -350)
            inv = nodes.new('ShaderNodeMath')
            inv.operation = 'SUBTRACT'
            inv.inputs[0].default_value = 1.0
            inv.location = (-370, -550)
            comb = nodes.new('ShaderNodeCombineColor')
            comb.location = (-170, -350)
            links.new(normal_color, sep.inputs[0])
            links.new(sep.outputs['Red'], comb.inputs['Red'])
            links.new(sep.outputs['Green'], inv.inputs[1])
            links.new(inv.outputs[0], comb.inputs['Green'])
            links.new(sep.outputs['Blue'], comb.inputs['Blue'])
            normal_color = comb.outputs[0]
        normal = nodes.new('ShaderNodeNormalMap')
        normal.location = (30, -200)
        links.new(normal_color, normal.inputs['Color'])
        normal_output = normal.outputs['Normal']
    if 'height' in textures:
        bump = nodes.new('ShaderNodeBump')
        bump.location = (30, -480)
        bump.inputs['Strength'].default_value = 0.2
        bump.inputs['Distance'].default_value = 0.01
        links.new(textures['height'], bump.inputs['Height'])
        if normal_output is not None:
            links.new(normal_output, bump.inputs['Normal'])
        normal_output = bump.outputs['Normal']
    if normal_output is not None:
        links.new(normal_output, shader.inputs['Normal'])


class AUTO_PBR_MATERIAL_OT_assign(bpy.types.Operator):
    bl_idname = 'auto_pbr_material.assign'
    bl_label = 'Assign PBR Materials'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        raw = context.scene.auto_pbr_folder
        if not raw.strip():
            self.report({'ERROR'}, 'Select a texture folder first')
            return {'CANCELLED'}
        folder = Path(bpy.path.abspath(raw)).expanduser()
        try:
            index = index_textures(folder)
        except OSError as exc:
            self.report({'ERROR'}, f'Cannot read texture folder: {exc}')
            return {'CANCELLED'}
        assigned = skipped = failed = 0
        old = set()
        completed = []
        details = []
        for obj in sorted(context.selected_objects, key=lambda o: o.name):
            if obj.type != 'MESH':
                continue
            if obj.library or obj.override_library:
                skipped += 1
                details.append(f'{obj.name}: linked object')
                continue
            maps, reason = find_textures(obj, index)
            if not maps:
                skipped += 1
                details.append(f'{obj.name}: {reason}')
                continue
            # Build first, so a texture loading error leaves existing slots intact.
            mat = bpy.data.materials.new(obj.name)
            try:
                build_material(mat, maps, context.scene.auto_pbr_directx)
            except Exception as exc:
                bpy.data.materials.remove(mat)
                failed += 1
                details.append(f'{obj.name}: {exc}')
                continue
            previous = {s.material for s in obj.material_slots if s.material}
            if obj.data.users > 1 or obj.data.library:
                obj.data = obj.data.copy()
            obj.data.materials.clear()
            obj.data.materials.append(mat)
            for slot in obj.material_slots:
                slot.link = 'DATA'
                slot.material = mat
            for poly in obj.data.polygons:
                poly.material_index = 0
            old.update(previous)
            assigned += 1
            completed.append((obj, mat))
        for mat in old:
            if mat.users == 0 and not mat.use_fake_user and not mat.library:
                bpy.data.materials.remove(mat)
        # Recover exact object names after removing replaced orphan materials.
        for obj, mat in completed:
            if bpy.data.materials.get(obj.name) is None:
                mat.name = obj.name
        if details:
            print('Auto PBR Material:\n' + '\n'.join(details))
        self.report({'WARNING'} if skipped or failed else {'INFO'},
                    f'{assigned} assigned, {skipped} skipped, {failed} failed' + ('; see console for details' if details else ''))
        return {'FINISHED'}


class AUTO_PBR_MATERIAL_PT_panel(bpy.types.Panel):
    bl_label = 'Auto PBR Material'
    bl_idname = 'AUTO_PBR_MATERIAL_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Auto PBR Material'

    def draw(self, context):
        self.layout.prop(context.scene, 'auto_pbr_folder', text='Texture Folder')
        self.layout.prop(context.scene, 'auto_pbr_directx', text='DirectX Normals')
        self.layout.operator('auto_pbr_material.assign')


def register():
    bpy.utils.register_class(AUTO_PBR_MATERIAL_OT_assign)
    bpy.utils.register_class(AUTO_PBR_MATERIAL_PT_panel)
    bpy.types.Scene.auto_pbr_folder = bpy.props.StringProperty(name='Texture Folder', subtype='DIR_PATH')
    bpy.types.Scene.auto_pbr_directx = bpy.props.BoolProperty(name='DirectX Normals', default=False,
        description='Flip green channel for normal maps without an explicit OpenGL or DirectX suffix')


def unregister():
    del bpy.types.Scene.auto_pbr_directx
    del bpy.types.Scene.auto_pbr_folder
    bpy.utils.unregister_class(AUTO_PBR_MATERIAL_PT_panel)
    bpy.utils.unregister_class(AUTO_PBR_MATERIAL_OT_assign)


if __name__ == '__main__':
    register()
