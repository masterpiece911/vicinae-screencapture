import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'assets'))
import feedback


class FeedbackTests(unittest.TestCase):
    def test_outline_never_overlaps_recorded_pixels(self):
        selection = (100, 80, 400, 240)
        rectangles = feedback.overlay_rectangles((0, 0, 1920, 1080), selection)
        self.assertEqual(len(rectangles), 4)
        for x, y, w, h in rectangles:
            self.assertTrue(x+w <= 100 or x >= 500 or y+h <= 80 or y >= 320)

    def test_monitor_edges_are_clipped(self):
        self.assertEqual(feedback.overlay_rectangles((0, 0, 1920, 1080), (0, 0, 1920, 1080)), [])
        for x, y, w, h in feedback.overlay_rectangles((-1920, 0, 1920, 1080), (-1910, 10, 200, 100)):
            self.assertGreaterEqual(x, -1920)
            self.assertLessEqual(x+w, 0)

    def test_flash_failure_does_not_fail_capture(self):
        with patch.object(feedback.subprocess, 'run', side_effect=subprocess.TimeoutExpired('flash', 3)):
            feedback.flash()

    def test_open_saved_detaches_and_keeps_path_as_one_argument(self):
        with patch.object(feedback.subprocess, 'Popen') as run:
            feedback.open_saved(Path('/tmp/file with spaces.png'))
        self.assertEqual(run.call_args.args[0][-2:], ['open', '/tmp/file with spaces.png'])
        self.assertTrue(run.call_args.kwargs['start_new_session'])

    def test_xdg_open_is_preferred(self):
        with patch.object(feedback.shutil, 'which', return_value='/usr/bin/xdg-open'), patch.object(feedback.subprocess, 'run') as run:
            feedback.open_file('/tmp/capture.gif')
        self.assertEqual(run.call_args.args[0], ['xdg-open', '/tmp/capture.gif'])

    def test_gio_fallback(self):
        with patch.object(feedback.shutil, 'which', side_effect=lambda name: '/usr/bin/gio' if name == 'gio' else None), patch.object(feedback.subprocess, 'run') as run:
            feedback.open_file('/tmp/capture.gif')
        self.assertEqual(run.call_args.args[0], ['gio', 'open', '/tmp/capture.gif'])

    def test_outline_cleanup_terminates_only_owned_child(self):
        child = Mock(); child.poll.return_value = None
        feedback.stop_outline(child)
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=2)
