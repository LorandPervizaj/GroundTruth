"""Compatibility and bounded regression controls for audited research/dev upgrades."""

import subprocess
import sys

import aiohttp
import black
import filelock
import msgpack
import pytest
import tldextract
from twisted.mail.imap4 import wildcardToRegexp


def test_imap_wildcards_escape_regex_operators():
    expression = wildcardToRegexp("(a+)+z", "/")
    assert expression.fullmatch("(a+)+z")
    assert expression.fullmatch("aaaaz") is None
    assert wildcardToRegexp("foo*", "/").fullmatch("foobar")


def test_research_and_tooling_interfaces(tmp_path):
    with (
        filelock.FileLock(tmp_path / "lock"),
        pytest.raises(filelock.Timeout),
        filelock.FileLock(tmp_path / "lock", timeout=0),
    ):
        pytest.fail("Exclusive file lock was not enforced")
    extractor = tldextract.TLDExtract(cache_dir=str(tmp_path / "cache"), suffix_list_urls=())
    assert extractor("https://synthetic.example.org").domain == "example"
    assert msgpack.unpackb(msgpack.packb({"synthetic": 1})) == {"synthetic": 1}
    assert black.format_str("x=1\n", mode=black.Mode()) == "x = 1\n"
    assert aiohttp.ClientTimeout(total=1).total == 1


def test_virtualenv_creates_usable_isolated_environment(tmp_path):
    target = tmp_path / "environment"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "virtualenv",
            "--no-download",
            "--no-periodic-update",
            "--app-data",
            str(tmp_path / "private-cache"),
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    executable = target / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    result = subprocess.run(
        [str(executable), "-m", "pip", "--version"], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
