# Breath of the Wild button prompts

The Mac menu bar has a **Button icons** menu with **Automatic**, **Switch**, **Xbox**, **PlayStation** and
**Keyboard**. Select a style, quit, and reopen the game. The checked choice is saved per profile in
`button-icons-style`; it does not modify the game's save data. This selector is in the Mac menu bar, not BotW's
in-game Options screen.

Automatic (the default) waits up to 1.5 seconds for initial controller discovery, with the main run loop free to
receive notifications. DualSense/DualShock selects PlayStation; Nintendo/Joy-Con selects Switch; Xbox and generic
extended gamepads select Xbox. No extended controller selects Keyboard. Connecting a different controller takes
effect at the next launch. Explicit saved choices override Automatic.

The build generates all three replacement font and Controls-picture sets from the player's own fonts and includes them in the app;
Switch uses the original fonts and pictures. Fonts are selected before the game loads them. A player mod replacing the same font
archive or `Pack/Bootup.pack` takes precedence and disables the built-in selector's overlays for that launch, with a message in the log.
If an earlier generated always-on font mod is installed, remove those seven font files and regenerate its manifest
(or remove it if no other mods remain) to let the menu control the style.

The Xbox and PlayStation labels follow the default controller mapping by position: Switch A/B/X/Y become Xbox
B/A/Y/X or PlayStation Circle/Cross/Triangle/Square. Custom controller remaps or `TOTK_FACE_BUTTONS=label` can disagree
with those prompts. Keyboard labels follow the launcher's default keys. The Controls screen also follows the selected style: light Xbox or DualSense illustrations with the native
blue group outlines and callouts moved to the corresponding inputs, or a keyboard illustration. Other fixed-image tutorials retain
their original artwork.

## Standalone mod

Older apps can still load a fixed style without rebuilding, using Python 3.14 with fonttools and Pillow:

```sh
python3.14 -m pip install fonttools==4.67.0 Pillow==12.3.0
python3.14 games/botw/scripts/make_button_icons.py \
  "$HOME/Library/Application Support/MacNativeGames/BotW/mods/botw190" \
  --app "/Applications/Breath of the Wild.app" --style xbox
```

Use `botw160` for a 1.6.0 app; use `playstation` or `keyboard` for other styles. Add `--replace` when changing a
previously generated mod. Quit and reopen the game to load it. Existing font mods are refused unless that
flag is given. Other files in the mod folder are kept and included in its manifest. The output includes seven font archives and `Pack/Bootup.pack`. Build tools can instead pass
`--romfs <folder> --shared-fonts <folder> --version botw190`, without a packaged app.

## Format and verification

BotW uses Yaz0-compressed font SARC archives, with `External_00.bffnt` bitmap font pages in BC4 Tegra block-linear
BNTX storage. The generator reuses the shared vector icon designs and the player's standard system font. It keeps
glyph cells, bearings, advance widths, font metadata, texture format and storage size unchanged, and replaces only
blocks that contain changed pixels. Every other archive member remains byte-identical. Original fonts must match
the checked geometry; unknown formats are refused.

All seven locale archives are handled, including the small CN/KR/TW/TH archives. Repacked archives have exactly the
original decompressed size, so the game's resource-size budgets need no changes. Yaz0 output uses literal groups;
it is larger on disk than Nintendo's compressed output, while its decoded size stays the same. The mod manifest
binds each replacement to the original archive's SHA-256.

Controls artwork replaces only two textures in `Layout/Common.sblarc` inside `Pack/Bootup.pack`. The allocated
texture storage, grayscale/alpha format, component mapping, tiling and decoded Common archive size stay unchanged. The layout and its animations place the native
callouts and group outlines at the drawn controls, including the expanded rear view, while preserving localized text and action visibility. Common is recompressed with
LZ77; the outer pack can grow slightly. Generation refuses a game whose resource table gives Bootup.pack a fixed
size budget. Other pack members remain byte-identical.

Synthetic tests cover Yaz0 roundtrips, BC4 decoding, grayscale/alpha picture encoding, controller storage, callout endpoints, unchanged font metadata and non-target glyph pixels, and refusal
of unfamiliar geometry. Native AppKit tests exercise all five choices, checkmarks, profile persistence, invalid-choice
fallback, and delayed controller discovery. Build tests check generation of all three styles for both game versions. Generation was also checked against the player's 1.9.0 fonts for all three styles. Xbox
prompts were checked in-game on Mac 1.9.0 using a private copy of the save. BotW 1.6.0 and non-English gameplay were
not available for in-game verification.

## Player-supplied controller artwork

The build reuses optional personal artwork from
`~/Library/Application Support/MacNativeGames/BotW/controller-art/<style>/`. Each style folder contains
`front.png` (580×340), `rear.png` (576×100), and `layout.json` with front anchors, optional group radii,
shoulder anchors and rear display geometry. Both images keep transparency. Imported Wii U textures must first
be decoded and converted; copying a Wii U Bootup.pack into this Switch build is not supported. Artwork hashes
are part of the build cache, so changing an image regenerates the affected sets on the next build.

The standalone generator also accepts `--controller-art <style-folder>`. This personal artwork is used only
on the local machine; downloaded mod assets are not checked into the repository.

## Custom merged icon sets

`TOTK_BUTTON_ICONS=/path/to/sets` selects manifests at `<root>/<style>/manifest.tsv`, including `switch`.
`TOTK_BUTTON_ICONS=0` disables the overlay. The launcher also discovers a `button-icons/` directory beside the
profile in the selected data folder. Each custom style must contain a complete, correctly merged pack when a
mod changes Bootup game data; a missing manifest or a collision with a player mod stops startup. This avoids
silently replacing mod game data with a vanilla controller-picture pack.
