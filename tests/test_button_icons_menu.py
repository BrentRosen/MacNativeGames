"""Native BotW menu, real profile persistence and delayed automatic controller discovery."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import build_app

ROOT=Path(__file__).resolve().parents[1]

class ButtonIconBuild(unittest.TestCase):
    def test_every_style_is_generated_for_the_selected_game_version(self):
        for version in ('botw160','botw190'):
            with self.subTest(version=version),patch.object(Path,'home',return_value=Path('/test/home')),patch.object(build_app,'sha256',return_value='source-hash'),patch.object(build_app,'run') as run:
                tree=Path('/test/totk');botw=Path('/test/botw');logs=Path('/test/logs')
                with patch.object(Path,'write_text'):
                    build_app.step_button_icons_botw(tree,botw,logs,version)
                self.assertEqual(run.call_count,3)
                for call,style in zip(run.call_args_list,('xbox','playstation','keyboard')):
                    args=call.args[0]
                    self.assertEqual(args[2],tree/f'extracted/{version}/romfs-button-icons/{style}')
                    self.assertEqual(args[args.index('--version')+1],version)
                    self.assertEqual(args[args.index('--style')+1],style)
                    self.assertIn('--replace',args)

    def test_personal_artwork_is_passed_only_to_its_selected_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            art=home/'Library/Application Support/MacNativeGames/BotW/controller-art/xbox'
            art.mkdir(parents=True)
            for name in ('front.png','rear.png','layout.json'):(art/name).write_bytes(b'fixture')
            with patch.object(Path,'home',return_value=home),patch.object(build_app,'sha256',return_value='hash'),patch.object(build_app,'run') as run,patch.object(Path,'write_text'):
                build_app.step_button_icons_botw(Path('/test/totk'),Path('/test/botw'),Path('/test/logs'),'botw190')
            args=run.call_args_list[0].args[0]
            self.assertEqual(args[args.index('--controller-art')+1],art)
            for call in run.call_args_list[1:]:self.assertNotIn('--controller-art',call.args[0])

@unittest.skipUnless(sys.platform=='darwin' and shutil.which('xcrun'),'requires macOS AppKit and Xcode tools')
class ButtonIconsMenu(unittest.TestCase):
    def test_menu_saved_choices_and_delayed_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);probe=tmp/'probe';gfx=ROOT/'games/totk/third_party/d2r_gfx/gfx/nvn/include'
            result=subprocess.run(['xcrun','clang','-std=gnu11','-fobjc-arc','-Wall','-Wextra','-Werror',
                '-Wno-deprecated-declarations','-DGAME_BOTW=1','-DGAME_BOTW190=1','-I'+str(gfx),
                '-Wl,-undefined,dynamic_lookup','-Wl,-dead_strip',str(ROOT/'games/totk/tests/button_icons_menu/probe.m'),
                '-framework','Cocoa','-framework','GameController','-framework','Metal','-framework','QuartzCore',
                '-framework','CoreVideo','-o',str(probe)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)
            for style in ('xbox','playstation','switch','keyboard'):
                with self.subTest(style=style):
                    profile=tmp/style
                    env=dict(os.environ,TOTK_PROFILE_DIR=str(profile),TOTK_UI_LANG='en')
                    result=subprocess.run([str(probe),style],capture_output=True,text=True,env=env,timeout=8)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertIn('pass: menu, saved choices, Automatic '+style,result.stdout)
                    self.assertEqual((profile/'button-icons-style').read_text(),'automatic')
