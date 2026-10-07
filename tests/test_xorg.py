import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'assets'))
import capture
import xorg


class SessionTests(unittest.TestCase):
    def test_xwayland_display_does_not_select_xorg(self):
        self.assertEqual(capture.session_type({'XDG_SESSION_TYPE': 'wayland', 'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-1'}), 'wayland')

    def test_explicit_x11_wins_over_stale_wayland_variable(self):
        self.assertEqual(capture.session_type({'XDG_SESSION_TYPE': 'x11', 'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'stale'}), 'x11')

    def test_environment_fallbacks(self):
        self.assertEqual(capture.session_type({'WAYLAND_DISPLAY': 'wayland-0', 'DISPLAY': ':0'}), 'wayland')
        self.assertEqual(capture.session_type({'DISPLAY': ':2'}), 'x11')
        with self.assertRaises(RuntimeError):
            capture.session_type({})

    def test_dependencies_do_not_cross_backends(self):
        wayland = capture.required_tools('wayland', 'screenshot', 'area', 'copy', 'none')
        x11 = capture.required_tools('x11', 'screenshot', 'area', 'copy', 'none')
        self.assertIn('grimshot', wayland)
        self.assertNotIn('maim', wayland)
        self.assertIn('maim', x11)
        self.assertIn('xclip', x11)
        self.assertNotIn('swaymsg', x11)
        self.assertNotIn('wl-copy', x11)
        self.assertNotIn('xclip', capture.required_tools('x11', 'screenshot', 'screen', 'save', 'none'))
        self.assertNotIn('maim', capture.required_tools('x11', 'record', 'area', 'save', 'none'))

    def test_pulseaudio_system_audio_selects_sink_monitor(self):
        with patch.object(capture.shutil, 'which', return_value='/usr/bin/pactl'), patch.object(capture, 'call', return_value='speaker') as run:
            self.assertEqual(capture.audio_device('system'), 'speaker.monitor')
            run.assert_called_once_with(['pactl', 'get-default-sink'])


class XorgTests(unittest.TestCase):
    def test_parse_multi_monitor_layout(self):
        text = 'Monitors: 2\n 0: +*eDP-1 1920/300x1080/200+0+0 eDP-1\n 1: +DP-1 2560/600x1440/400+1920+0 DP-1'
        self.assertEqual(xorg.monitors(text), [(0, 0, 1920, 1080), (1920, 0, 2560, 1440)])

    def test_partial_offscreen_window_clips_to_desktop(self):
        self.assertEqual(xorg.clip((-20, -10, 100, 60), (0, 0, 1920, 1080)), (0, 0, 80, 50))
        with self.assertRaises(RuntimeError):
            xorg.clip((2000, 0, 10, 10), (0, 0, 1920, 1080))

    def test_current_monitor_uses_active_window(self):
        with patch.object(xorg, 'monitors', return_value=[(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]), patch.object(xorg, 'active_rect', return_value=(2200, 50, 500, 500)):
            self.assertEqual(xorg.current_monitor(), (1920, 0, 1920, 1080))

    def test_cancelled_selection_never_captures(self):
        runner = Mock(return_value=(1, '', 'Selection was cancelled by keystroke.'))
        with self.assertRaises(capture.Cancelled):
            xorg.select_rect('area', runner, capture.Cancelled)

    def test_selection_error_is_not_silently_cancelled(self):
        runner = Mock(return_value=(1, '', 'Cannot open display'))
        with self.assertRaisesRegex(RuntimeError, 'Cannot open display'):
            xorg.select_rect('area', runner, capture.Cancelled)

    def test_area_and_window_have_distinct_selection_modes(self):
        for target, tolerance in [('area', '0'), ('window', '9999999')]:
            runner = Mock(return_value=(0, '10,20 101x99', ''))
            with patch.object(xorg, 'desktop_rect', return_value=(0, 0, 1920, 1080)):
                self.assertEqual(xorg.select_rect(target, runner, capture.Cancelled), (10, 20, 101, 99))
            self.assertIn(tolerance, runner.call_args.args[0])

    def test_xorg_recording_with_audio_and_odd_size(self):
        with patch.dict(os.environ, {'DISPLAY': ':3'}):
            args = xorg.recording_command((10, 20, 101, 99), Path('/tmp/file with spaces.mp4'), 'speaker.monitor')
        self.assertEqual(args[0], 'ffmpeg')
        self.assertIn('x11grab', args)
        self.assertIn(':3', args)
        self.assertIn('speaker.monitor', args)
        self.assertIn('pad=ceil(iw/2)*2:ceil(ih/2)*2', args)
        self.assertEqual(args[-1], '/tmp/file with spaces.mp4')

    def test_xorg_screenshot_geometry(self):
        self.assertEqual(xorg.screenshot_command((1920, 0, 800, 600))[-1], '800x600+1920+0')


if __name__ == '__main__':
    unittest.main()
