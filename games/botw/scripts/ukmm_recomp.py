#!/usr/bin/env python3
"""Use U-King Mod Manager (UKMM) in Wii U mode with BotW Recompiled (/Applications/BotW Recompiled.app).

The recompiled app reads its game from Contents/Resources/game (code/, content/, aoc/, meta/: the Wii U title with the
1.5.0 update already merged in), or from the folder in the BOTW_GAME environment variable. It has no mod overlay, so
this script builds a modded copy of that folder, with no change to the app:

  sync   run after every UKMM deploy (UKMM's "Launch game" command runs it with --launch):
           - makes <game> an APFS clone of the app's game folder (first run only; clones take no extra space);
           - puts back the stock files the last sync replaced, then clones UKMM's deploy (content/ and aoc/, layout
             with or without the mod name) over <game>, and records what it replaced in <game>/.ukmm.json;
           - adds the text packs (Pack/Bootup_<lang>.pack) from UKMM's merge folder: UKMM 0.17 merges a mod's EUen
             text into the USen pack there but its deploy looks for the mod's own pack name and skips it;
           - with --launch, opens the app with BOTW_GAME=<game>.
  install  puts a launcher in front of the app's executable (renamed to BotWRecomp-bin) so opening the app from the
           Finder plays <game> too: it runs sync first when UKMM deployed since the last one, and falls back to the
           stock game while there is no <game>. Run again after replacing the app.

UKMM settings (Wii U mode): Base game and Update folders both <app>/Contents/Resources/game/content, DLC folder
<app>/Contents/Resources/game/aoc/0010 (the folder holding Pack/AocMainField.pack); deploy method Copy or Hard Link; no Cemu rules.txt needed.

usage: ukmm_recomp.py sync --deploy <UKMM deploy folder> [--app <BotW Recompiled.app>] [--game <folder>] [--launch]
       ukmm_recomp.py install [--app <BotW Recompiled.app>] [--deploy <folder>] [--game <folder>]
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys

DEFAULT_APP = Path('/Applications/BotW Recompiled.app')
DEFAULT_GAME = Path.home() / 'Library/Application Support/BotWRecomp/ukmm-game'
DEFAULT_DEPLOY = Path.home() / 'Library/Application Support/BotWRecomp/ukmm-deploy'
LAUNCHER_TAG = '# BotW Recompiled UKMM launcher'
LAUNCHER = '''#!/bin/sh
{tag} (written by {script} install; the app itself is {exe}-bin)
here="$(cd "$(dirname "$0")" && pwd)"
game={game}
deploy={deploy}
if [ -z "$BOTW_GAME" ] && [ -f "$game/code/U-King.rpx" ]; then
  record="$game/{record}"
  # UKMM keeps the mods' file times, so look at change times: anything deployed since the last sync means sync again
  if [ -d "$deploy" ] && {{ [ ! -f "$record" ] || [ -n "$(find "$deploy" -cnewer "$record" -print -quit)" ]; }}; then
    {python} {script} sync --deploy "$deploy" --game "$game" >> "$game/../ukmm-sync.log" 2>&1
  fi
  export BOTW_GAME="$game"
fi
exec "$here/{exe}-bin" "$@"
'''
NAMED = 'BreathOfTheWild_UKMM'      # the "with name" deploy layout
FOLDERS = ('content', 'aoc')        # what UKMM's Wii U deploy writes (aoc holds 0010/)
RECORD = '.ukmm.json'
UKMM_SETTINGS = Path.home() / 'Library/Application Support/ukmm/settings.yml'
TEXT_PACKS = 'content/Pack/Bootup_????.pack'


def ukmm_merged():
    """UKMM's Wii U merge folder (<storage>/wiiu/profiles/<profile>/merged), or None without UKMM settings."""
    if not UKMM_SETTINGS.is_file():
        return None
    storage, profile, section = None, 'Default', None
    for line in UKMM_SETTINGS.read_text().splitlines():
        if not line.startswith(' '):
            section = line.split(':')[0]
        key, _, value = line.strip().partition(': ')
        if line.startswith('storage_dir: '):
            storage = Path(value)
        elif section == 'wiiu_config' and line.startswith('  profile: '):
            profile = value
    return storage / 'wiiu/profiles' / profile / 'merged' if storage else None


class UkmmError(Exception):
    pass


def clone(src, dst):
    """APFS clone of a file or folder (cp -c), falling back to a plain copy on other file systems."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if subprocess.run(['/bin/cp', '-c', str(src), str(dst)], capture_output=True).returncode:
        shutil.copy2(src, dst)


def deploy_root(deploy):
    """The folder holding content/ and aoc/ in a deploy, for either layout."""
    for root in (deploy, deploy / NAMED):
        if any((root / f).is_dir() for f in FOLDERS):
            return root
    raise UkmmError(f'{deploy}: no content/ or aoc/ folder in it (deploy from UKMM first)')


def deployed_files(root):
    """Relative paths (content/..., aoc/...) of every file in the deploy; symbolic links are followed."""
    files = []
    for folder in FOLDERS:
        top = root / folder
        if not top.is_dir():
            continue
        for dirpath, _, names in os.walk(top, followlinks=True):
            for name in names:
                if name != '.DS_Store':
                    files.append((Path(dirpath) / name).relative_to(root).as_posix())
    return sorted(files)


def make_game(base, game):
    """<game> as a clone of the app's game folder, made once."""
    if (game / 'code/U-King.rpx').is_file():
        return
    if game.exists():
        raise UkmmError(f'{game}: exists but is not a game folder; move it aside first')
    print(f'cloning {base} to {game} (first run)')
    part = game.with_name(game.name + '.part')
    if part.exists():
        shutil.rmtree(part)
    game.parent.mkdir(parents=True, exist_ok=True)
    if subprocess.run(['/bin/cp', '-cR', str(base), str(part)]).returncode:
        raise UkmmError(f'cannot copy {base} to {part}')
    part.rename(game)


def sync(app, deploy, game):
    base = app / 'Contents/Resources/game'
    if not (base / 'code/U-King.rpx').is_file():
        raise UkmmError(f'{app}: no game in Contents/Resources/game')
    root = deploy_root(deploy)
    make_game(base, game)

    record = game / RECORD
    previous = json.loads(record.read_text())['files'] if record.is_file() else []
    for rel in previous:                    # back to stock first, so a mod taken out leaves nothing behind
        target = game / rel
        if (base / rel).is_file():
            clone(base / rel, target)
        elif target.is_file():
            target.unlink()

    sources = {rel: root / rel for rel in deployed_files(root)}
    merged = ukmm_merged()
    if merged and merged.is_dir():
        for pack in merged.glob(TEXT_PACKS):
            sources.setdefault(pack.relative_to(merged).as_posix(), pack)
    files = sorted(sources)
    for rel in files:
        clone(sources[rel], game / rel)
    record.write_text(json.dumps({'deploy': str(root), 'files': files}, indent=1))
    added = sum(not (base / rel).is_file() for rel in files)
    print(f'{len(files)} modded files in {game} ({len(files) - added} replaced, {added} new); '
          f'{len(set(previous) - set(files))} put back to stock')


def launch(app, game):
    subprocess.run(['/usr/bin/open', '-n', '-a', str(app), '--env', f'BOTW_GAME={game}'], check=True)


def install(app, deploy, game):
    exe = plistlib.loads((app / 'Contents/Info.plist').read_bytes())['CFBundleExecutable']
    path = app / 'Contents/MacOS' / exe
    real = path.with_name(exe + '-bin')
    if not (path.is_file() and LAUNCHER_TAG in path.read_bytes()[:200].decode('latin-1')):
        if not path.is_file():
            raise UkmmError(f'{path}: no executable')
        path.replace(real)                  # a renamed Mach-O keeps its embedded signature
    elif not real.is_file():
        raise UkmmError(f'{path} is the launcher but {real.name} is missing; reinstall the app')
    path.write_text(LAUNCHER.format(tag=LAUNCHER_TAG, exe=exe, game=shlex.quote(str(game)),
                                    deploy=shlex.quote(str(deploy)), record=RECORD,
                                    python=shlex.quote(sys.executable), script=shlex.quote(str(Path(__file__).resolve()))))
    path.chmod(0o755)
    print(f'{path}: launcher installed (the app opens {game} when it exists)')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('sync', help='apply a UKMM deploy to the modded game folder')
    p.add_argument('--deploy', type=Path, required=True)
    p.add_argument('--app', type=Path, default=DEFAULT_APP)
    p.add_argument('--game', type=Path, default=DEFAULT_GAME)
    p.add_argument('--launch', action='store_true')
    p = sub.add_parser('install', help='make the app open the modded game folder when opened from the Finder')
    p.add_argument('--app', type=Path, default=DEFAULT_APP)
    p.add_argument('--deploy', type=Path, default=DEFAULT_DEPLOY)
    p.add_argument('--game', type=Path, default=DEFAULT_GAME)
    args = parser.parse_args()
    try:
        if args.command == 'install':
            install(args.app, args.deploy.expanduser(), args.game.expanduser())
            return
        sync(args.app, args.deploy.expanduser(), args.game.expanduser())
        if args.launch:
            launch(args.app, args.game.expanduser())
    except UkmmError as e:
        sys.exit(f'error: {e}')


if __name__ == '__main__':
    main()
