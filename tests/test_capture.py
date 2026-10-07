import importlib.util
from pathlib import Path
import struct
import sys
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'assets'))

spec = importlib.util.spec_from_file_location('capture', Path(__file__).parents[1] / 'assets/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(capture, 'session_type', return_value='wayland')
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(capture.shutil, 'which', side_effect=lambda name: None if name == 'pactl' else '/usr/bin/' + name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def options(self):
        return SimpleNamespace(delay=0, target='area', destination='copy')

    def test_cancel_does_not_touch_clipboard(self):
        with patch.object(capture.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr=b'')) as run:
            capture.screenshot(self.options())
            self.assertEqual(run.call_count, 1)

    def test_failed_grimshot_does_not_touch_clipboard(self):
        with patch.object(capture.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr=b'failed')) as run:
            with self.assertRaises(RuntimeError):
                capture.screenshot(self.options())
            self.assertEqual(run.call_count, 1)

    def test_png_trailing_filename_not_copied(self):
        data = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 0) + b'IEND' + b'\0'*4
        copied = []
        def run(command, **kwargs):
            if command[0] == 'grimshot':
                kwargs['stdout'].write(data + b'-\n')
            else:
                copied.append(kwargs['input'])
            return SimpleNamespace(returncode=0, stderr=b'')
        with patch.object(capture.subprocess, 'run', side_effect=run), patch.object(capture, 'notify'):
            capture.screenshot(self.options())
        self.assertEqual(copied, [data])

    def test_system_audio_uses_monitor_not_microphone(self):
        with patch.object(capture, 'call', return_value='node.name = "speaker"'):
            self.assertIn('--audio=speaker.monitor', capture.audio_source('system'))
            self.assertIn('--audio=speaker', capture.audio_source('microphone'))
        self.assertEqual(capture.audio_source('none'), [])

    def test_no_audio_device_is_error(self):
        with patch.object(capture, 'call', return_value=''):
            with self.assertRaises(RuntimeError):
                capture.audio_source('system')

    def test_recording_handles_odd_dimensions_and_negative_coordinates(self):
        command = capture.recording_command('DP-1', '-1440,0 101x99', Path('/tmp/space name.mp4'), 'none')
        self.assertIn('pad=ceil(iw/2)*2:ceil(ih/2)*2', command)
        self.assertIn('-1440,0 101x99', command)
        self.assertIn('/tmp/space name.mp4', command)

    def test_stale_socket_status_is_idle(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(capture, 'RUNTIME', Path(folder)):
            self.assertEqual(capture.request('status'), {})


if __name__ == '__main__':
    unittest.main()
