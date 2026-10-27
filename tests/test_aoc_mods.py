"""Exercise the real native DLC overlay loader with synthetic images and integrity failures."""
from pathlib import Path
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(sys.platform=='darwin' and shutil.which('clang'),'requires macOS CommonCrypto')
class DlcMods(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.build=tempfile.TemporaryDirectory();d=Path(cls.build.name);cls.exe=d/'probe'
  p=subprocess.run(['clang','-DGAME_BOTW190','-DGAME_BOTW','-Wno-deprecated-declarations','-I',str(d),'-I',str(ROOT/'games/totk/runtime'),'-I',str(ROOT/'games/totk/third_party/d2r_gfx/gfx/nvn/include'),str(ROOT/'tests/test_aoc_mods.c'),'-framework','CoreFoundation','-o',str(cls.exe)],capture_output=True,text=True)
  if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 @classmethod
 def tearDownClass(cls):cls.build.cleanup()
 def fixture(self,d):
  (d/'image').write_bytes(b'ORIGINALKEEP');names=b'Base.bin\0Keep.bin\0'
  (d/'index').write_bytes(struct.pack('<8sQQ',b'TOTKRFS1',2,72)+struct.pack('<QQII',0,8,0,9)+struct.pack('<QQII',8,4,9,9)+names)
  root=d/'mods-aoc';m=root/'1';(m/'Added').mkdir(parents=True)
  lines=[]
  for name,data,old in [('Base.bin',b'MODDATA',b'ORIGINAL'),('Added/New.bin',b'ADDED',None)]:
   (m/name).write_bytes(data);lines.append(f'{name}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}\t{hashlib.sha256(old).hexdigest() if old else "-"}')
  (m/'manifest.tsv').write_text('\n'.join(lines)+'\n');return root
 def run_probe(self,d,root,mode='mods'):
  env=dict(os.environ);env.pop('TOTK_AOC_MODS',None)
  return subprocess.run([str(self.exe),str(d/'image'),str(d/'index'),str(root),mode],capture_output=True,text=True,env=env)
 def test_overlays_and_vanilla_and_implicit_path(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);root=self.fixture(d)
   for mode,path in [('mods',root),('vanilla',root),('implicit',d/'mods')]:
    p=self.run_probe(d,path,mode);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
 def test_changed_open_file_stops_read(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);root=self.fixture(d);p=self.run_probe(d,root,'mutate');self.assertEqual(p.returncode,2);self.assertIn('changed while the game ran',p.stderr)
 def test_bad_manifests_are_refused(self):
  for kind in ('sha','original','duplicate','traversal','size'):
   with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp);root=self.fixture(d);f=root/'1/manifest.tsv';s=f.read_text()
    if kind=='sha':s=s.replace(hashlib.sha256(b'MODDATA').hexdigest(),'0'*64)
    elif kind=='original':s=s.replace(hashlib.sha256(b'ORIGINAL').hexdigest(),'0'*64)
    elif kind=='duplicate':s+=s.splitlines()[0]+'\n'
    elif kind=='traversal':s=s.replace('Base.bin','../Base.bin')
    else:s=s.replace('Base.bin\t7','Base.bin\t9')
    f.write_text(s);p=self.run_probe(d,root);self.assertEqual(p.returncode,2,p.stdout+p.stderr)
