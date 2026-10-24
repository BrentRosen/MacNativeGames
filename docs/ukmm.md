# UKMM with Breath of the Wild

[U-King Mod Manager](https://github.com/GingerAvalanche/ukmm) (UKMM) merges Breath of the Wild RomFS mods - UKMM
mods, BNPs and graphic-pack style folders - and deploys the result in the Switch layout. The app loads RomFS mods from
a folder with a `manifest.tsv` ([player mods](mods.md#breath-of-the-wild)). `games/botw/scripts/ukmm.py` connects
the two. The app is not changed, and no game file other than the app's own data is needed.

UKMM handles RomFS only: a mod's `exefs/` is not read by UKMM, so code patches are not part of this.

## Setup (once)

1. Download UKMM for Apple silicon (`ukmm-aarch64-apple-darwin.tar.xz`) from its
   [releases](https://github.com/GingerAvalanche/ukmm/releases). Tested with 0.17.0.
2. Unpack the app's RomFS for UKMM to merge against (about 15 GB for 1.9.0 with its DLC; seconds on the same APFS
   volume):

   ```sh
   python3.14 games/botw/scripts/ukmm.py dump \
     --output "$HOME/Library/Application Support/MacNativeGames/BotW/ukmm-dump"
   ```

   `--app` names the app when it is not `/Applications/Breath of the Wild.app`. Run it again after an app of another
   game version is installed.
3. In UKMM, Settings > Switch:
   - Base game folder and Update folder: both `<dump>/romfs` (the app's RomFS already holds base + update);
   - DLC folder: `<dump>/dlc`;
   - Language: the game's language (`USen` for an `en-US` app; see [Breath of the Wild](mods.md#breath-of-the-wild));
   - Deploy method: **Copy** or **Hard Link**, not Symlink;
   - Deploy layout: either;
   - Output folder: any empty folder, for example
     `~/Library/Application Support/MacNativeGames/BotW/ukmm-deploy`;
   - Command to launch the game:

     ```text
     /opt/homebrew/bin/python3.14 "<repository>/games/botw/scripts/ukmm.py" sync --deploy "<output folder>" --launch
     ```

## Playing

Install and order mods in UKMM as usual, then press **Deploy**. Once, install the login agent that runs `sync` after
every deploy:

```sh
python3.14 games/botw/scripts/ukmm.py install-watcher \
  --deploy "$HOME/Library/Application Support/MacNativeGames/BotW/ukmm-deploy"
```

It watches UKMM's `nx/pending.yml`. UKMM rewrites that file with every list empty when a deploy is done. A minute
later (with a large mod like Second Wind) a notification says the game is ready to open from Finder. Its log is
`<data>/ukmm-sync.log`, and `uninstall-watcher` removes it. Without the agent, UKMM's launch button (the command above)
or a manual `sync` does the same.

`sync` must have run after every deploy: the game checks the SHA-256 of every mod file at start, so opening the app
after a deploy without one stops the start with `RomFS overlay integrity mismatch`. A `sync` when nothing changed
since the last one (the fingerprint of the deploy and icon files in `<data>/ukmm-sync.json`) only says so, so the
launch button stays quick. `sync` refuses to run while the game is running.

What `sync` does:

- Points `<data>/mods/<version>` at `<output>/01007EF00011E000/romfs` and `<data>/mods/<version>-aoc/1` at
  `<output>/01007EF00011F001/romfs` with symbolic links. A mod folder that already holds files is moved aside as
  `<version>.backup-<date>-<time>`, never deleted.
- Rebuilds the resource size table (`System/Resource/ResourceSizeTable.product.srsizetable`). UKMM starts it from the
  stock 1.6.0 table built into its `rstb` crate, not from the game dump (`deploy.rs`, `apply_rstb`). On 1.9.0 that
  table gives some resources a smaller size than the game needs, and the game crashes at start. `sync` starts from
  the app's own table instead, and changes only the entries for resources the deploy holds (files, and members of the
  archives in it):
  - each gets the larger of the two sizes;
  - an entry UKMM removed stays removed. UKMM removes the entry of a resource whose size it cannot calculate, so the
    game sizes it from the file;
  - DLC resources are named `Aoc/0010/<path>`, members of DLC archives included (the map units in
    `Pack/AocMainField.pack`).

  UKMM's own table is kept next to the rewritten one as `<name>.mod-original`, and `<data>/ukmm-sync.json` records
  what `sync` wrote, so a second `sync` without a new deploy starts from UKMM's table again.
- Writes both manifests with `games/totk/scripts/make_mod_manifest.py`. When the folder changes nothing, it removes
  the manifest, so the folder means "no mod".
- Merges `Pack/Bootup.pack` with the button-icon sets in `<data>/button-icons`. Each set replaces `Pack/Bootup.pack`
  too: its `Layout/Common.sblarc` carries the icons and the quick-menu fix, and two overlays cannot replace one file.
  - Each set's own copy is kept next to it as `Pack/Bootup.pack.icons`, with its manifest as `manifest.tsv.icons`.
  - The set then carries UKMM's `Bootup.pack` with the set's changed members put back in, and the mod manifest leaves
    `Bootup.pack` out.
  - UKMM writes every member of a pack it deploys again, so members are compared after decompression.
  - When both change the same member, the merge goes inside it: an archive member by member, a texture bank
    texture by texture. Second Wind changes two logo textures in `Layout/Common.sblarc`'s texture bank, and the icon
    sets change two controller pictures, five animations and a layout there, so all of it is kept. The archive is
    encoded again by reusing the mod's own Yaz0 tokens wherever they still give the same bytes, so it keeps about its
    compressed size. Plain literals made `Bootup.pack` 30 MB larger and the game crashed at the title.
  - When both change the same file, or the same texture, the mod's version is kept and `sync` names it. Any other
    path both replace (a font, say) goes to the mod.
  - A deploy without `Bootup.pack` puts the sets back as they were. A set written again later (an app update) is
    taken as the set's new own copy.
- With `--launch`, opens the app.

## Notes

- **Game version:** UKMM and most mods target Switch 1.6.0. The merge runs against the 1.9.0 dump, but whether a mod
  works on 1.9.0 is still the mod's question.
- **First merge on a new Switch profile:** UKMM 0.17.0 fails to clear a `merged` folder that does not exist yet, so
  Apply and Deploy do nothing. On the command line this shows as `failed to remove directory
  .../nx/profiles/Default/merged`. Creating that folder once fixes it.
- **Second Wind:** the released v1.9.10a BNP needs a UI repair for 1.9.0 (`tools/port_botw190.py` on the
  `fix/botw-1.9.0-compatibility` branch of BrentRosen/Second-Wind-Switch). Repair its `Pack/Bootup.pack` against the
  1.9.0 `Bootup.pack` from the dump, repack the BNP, and install that.
- **UKMM settings file:** UKMM's `settings.yml` rejects an `endian:` key under the Switch dump, and then falls back to
  default settings without saying so.

Tested 2026-10-23 on the 1.9.0 app with both DLC packs, Keyboard icons and UKMM 0.17.0. The test mod changed a member
of `Bootup.pack` and one DLC file. The base mod, the DLC mod and the merged icon set all loaded, and a save loaded
into the game world. Without the size-table rebuild, the same deploy crashed at start (`main+0x1506a38`).

Second Wind v1.9.10a (UI-repaired BNP, 4,016 base and 172 DLC files) loaded into the world and ran. Before the DLC
member names got their `Aoc/0010/` prefix, the merged `Pack/AocMainField.pack` crashed the game at the title screen
(`main+0x10b62c8`): its larger map units kept their 1.9.0 sizes.
