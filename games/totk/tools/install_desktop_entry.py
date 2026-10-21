#!/usr/bin/env python3
"""Install one desktop link to the packaged Mac app, preserving legacy saves."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

BUNDLE_ID = 'org.macnativegames.totk'
APPS = {
    BUNDLE_ID: ('Tears of the Kingdom', 'TOTK'),
    'org.macnativegames.botw': ('Breath of the Wild', 'BotW'),
}
LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'


def manifest(folder):
    result = {}
    for p in folder.rglob('*'):
        if p.is_file():
            with p.open('rb') as stream:
                result[str(p.relative_to(folder))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def install(app, desktop=None, data=None, register=True):
    app = app.resolve()
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    game = APPS.get(info.get('CFBundleIdentifier'))
    if not game or not (app/'Contents/MacOS'/info.get('CFBundleExecutable', '')).is_file():
        raise ValueError('requires a packaged MacNativeGames TOTK or BotW app')
    name, folder = game
    desktop = desktop if desktop is not None else Path.home()/'Desktop'/f'{name}  Mac.app'
    data = (data if data is not None else Path.home()/'Library/Application Support/MacNativeGames'/folder).resolve()
    data.mkdir(parents=True, exist_ok=True)
    report = dict(app=str(app), desktop=str(desktop), version=info['CFBundleShortVersionString'],
                  profile=str(data/'profile'), status='already-linked')
    if desktop.exists() and desktop.resolve() == app:
        report['status'] = 'already-linked' if desktop.is_symlink() else 'already-app'
        if register:
            subprocess.run([LSREGISTER, '-f', str(app)], check=True)
        return report
    old_info = desktop/'Contents/Info.plist'
    legacy = plistlib.loads(old_info.read_bytes()) if old_info.is_file() else {}
    source = Path(legacy['TOTKProfileDirectory']).expanduser().resolve() if legacy.get('TOTKProfileDirectory') else None
    profile = data/'profile'
    if source and source != profile and source.is_dir():
        before = manifest(source)
        if profile.exists() and manifest(profile) != before:
            raise ValueError('canonical and legacy profiles differ; neither was overwritten')
        if not profile.exists():
            staging = data/'profile.desktop-copy'
            if staging.exists():
                raise ValueError('unfinished profile copy exists; original desktop entry is unchanged')
            shutil.copytree(source, staging)
            if manifest(staging) != before or manifest(source) != before:
                raise ValueError('profile copy verification failed; original entry is unchanged')
            staging.rename(profile)
        backup = data/('profile-before-'+info['CFBundleShortVersionString'])
        if not backup.exists():
            shutil.copytree(profile, backup)
            if manifest(backup) != before:
                raise ValueError('upgrade backup verification failed; original entry is unchanged')
        if manifest(source) != before:
            raise ValueError('legacy source changed during migration; original entry is unchanged')
        report.update(legacy_profile=str(source), migrated_files=len(before),
                      upgrade_backup=str(backup), source_unchanged=True)
        (data/'profile-migration-manifest.json').write_text(json.dumps(
            dict(source=str(source), files=before), indent=2)+'\n')
    if desktop.exists() or desktop.is_symlink():
        backups = data/'desktop-entry-backups'
        backups.mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = backups/('entry-'+stamp)  # no .app suffix: no second launch entry
        if register:
            subprocess.run([LSREGISTER, '-u', str(desktop)], check=True)
        shutil.move(str(desktop), str(backup))
        report['previous_entry_backup'] = str(backup)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.symlink_to(app, target_is_directory=True)
    if register:
        subprocess.run([LSREGISTER, '-f', str(app)], check=True)
    report['status'] = 'installed'
    (data/'desktop-install.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--desktop', type=Path, help='desktop link path (default: selected game name)')
    parser.add_argument('--data', type=Path, help='data folder (default: selected game under Application Support/MacNativeGames)')
    args = parser.parse_args()
    print(json.dumps(install(args.app, args.desktop, args.data), indent=2))


if __name__ == '__main__':
    main()
