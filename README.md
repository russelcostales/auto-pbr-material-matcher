# Auto PBR Material

A lightweight Blender add-on that matches exported PBR textures to selected objects and automatically builds Principled BSDF materials.

## Installation

1. Download `auto_pbr_material.py`.
2. In Blender, open Edit > Preferences > Add-ons > Install from Disk.
3. Select the Python file and enable the add-on.

## Usage

1. Select mesh objects in Object Mode.
2. Press `N` and open the Auto PBR Material tab.
3. Choose the texture export folder.
4. Enable DirectX Normals if your unnamed normal format is DirectX (otherwise OpenGL is assumed).
5. Click **Assign PBR Materials**.

## Naming

For an object named `Lantern`, example texture filenames are:

- `Lantern_ColorMap.png`
- `Lantern_NormalMap.png`
- `Lantern_RoughnessMap.png`
- `Lantern_MetallicMap.png`

BaseColor, Metallic, Roughness, Normal, Height, AO, Emissive and Opacity naming variants are also supported. Matching is case-insensitive, with a fallback to an existing material name. Duplicate maps and unmatched objects are skipped.

Matched objects receive one material, replacing their existing material slots. Unselected objects are preserved. Height maps use bump mapping and AO is multiplied into base color. Textures remain linked to their original files. Packed channel maps, UDIMs and nested folders are not supported.

## Compatibility

Designed for Blender 4.2+.
