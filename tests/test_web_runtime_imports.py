"""The production CLI must import without optional scraping dependencies."""
import subprocess
import sys


def test_public_cli_does_not_import_optional_parsel():
    code = '''
import importlib.abc, sys
class RejectResearch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "parsel" or fullname.startswith("parsel."):
            raise AssertionError("Public CLI imported optional research parser")
sys.meta_path.insert(0, RejectResearch())
from groundtruth.cli import app
assert app is not None
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
