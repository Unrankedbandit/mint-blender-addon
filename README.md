# Mint Blender Add-on

Browse and import your Mint AI generated assets directly inside Blender.

The Mint add-on adds a small Mint panel to Blender's 3D View sidebar. After you
connect your Mint account, you can browse your generated models, worlds, and
asset packs, then import supported assets into the current Blender scene.

## Requirements

- Blender 4.2 or newer
- A Mint account: https://mint.gg
- Kiri Engine 3DGS Render for viewing Mint world splats:
  https://github.com/Kiri-Innovation/3dgs-render-blender-addon

Kiri is only needed for Gaussian splat worlds. GLB model imports work without
Kiri.

## Install

1. Download the Mint Blender add-on zip.
2. In Blender, open `Edit > Preferences > Add-ons`.
3. Click the install button and choose the zip file.
4. Enable `Mint Asset Browser`.
5. Open the 3D View sidebar and select the `Mint` tab.

## Use

1. Click `Log In` and complete the Mint sign-in flow in your browser.
2. Click `Refresh` if your assets do not appear right away.
3. Use `Models`, `Worlds`, or `Packs` to browse your Mint assets.
4. Click `Import GLB` for models.
5. Click `View Splat` for worlds when Kiri is installed.

## Splat Controls

After a world splat is imported, the `Active Splat` section lets you switch
between:

- `Render Mode`: camera-updated Kiri preview
- `Point Cloud`: editable point cloud mode for selecting and transforming the
  splat object

Use `Update View` or `Auto Update` when the rendered preview should follow your
current viewport.

## Troubleshooting

- If world rows say `Kiri required`, install and enable the Kiri add-on.
- If sign-in fails, log out and connect again.
- If a model says `No durable GLB yet`, that asset does not currently have an
  import-ready GLB.
- If a splat import fails, check Blender's terminal output and the Mint Kiri log
  at `~/.cache/mint-blender/logs/kiri-bridge.log`.

## Links

- Mint: https://mint.gg
- Kiri Engine 3DGS Render:
  https://github.com/Kiri-Innovation/3dgs-render-blender-addon
