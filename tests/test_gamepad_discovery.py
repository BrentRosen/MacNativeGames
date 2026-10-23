"""Automatic artwork waits for delayed native controller enumeration without blocking the main queue."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TOTK = Path(__file__).resolve().parents[1] / 'games/totk'


@unittest.skipUnless(shutil.which('xcrun'), 'needs the Xcode command line tools')
class GamepadDiscoveryTests(unittest.TestCase):
    def test_delayed_controller_and_bounded_keyboard_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / 'probe'
            build = subprocess.run(['xcrun', 'clang', '-std=gnu11', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                                    str(TOTK / 'tests/gamepad_discovery/probe.m'), '-framework', 'Foundation',
                                    '-framework', 'GameController', '-framework', 'IOKit', '-o', str(probe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            for style in ('xbox', 'playstation', 'switch', 'keyboard'):
                with self.subTest(style=style):
                    run = subprocess.run([str(probe), style], capture_output=True, text=True, timeout=5)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    result = json.loads(run.stdout)
                    self.assertEqual(result['status'], 'pass')
                    self.assertEqual(result['style'], style)
