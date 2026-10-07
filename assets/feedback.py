#!/usr/bin/env python3
"""Brief, input-transparent capture feedback and asynchronous file opening."""
import os
import signal
import re
from pathlib import Path
import shutil
import subprocess
import sys


def flash():
    # Wait until the overlay is gone so a subsequent recording never captures it.
    try:
        subprocess.run([sys.executable, __file__, 'flash'], timeout=3,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        print(f'Capture flash unavailable: {error}', file=sys.stderr)


def start_outline(geometry):
    try:
        return subprocess.Popen([sys.executable, __file__, 'outline', geometry],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError as error:
        print(f'Recording outline unavailable: {error}', file=sys.stderr)
        return None


def stop_outline(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def open_saved(path):
    try:
        subprocess.Popen([sys.executable, __file__, 'open', str(Path(path).resolve())],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as error:
        print(f'File saved, but could not start its viewer: {error}', file=sys.stderr)


def open_file(path):
    if shutil.which('xdg-open'):
        command = ['xdg-open', path]
    elif shutil.which('gio'):
        command = ['gio', 'open', path]
    else:
        command = None
    try:
        if not command:
            raise RuntimeError('Install xdg-utils or configure a default viewer')
        subprocess.run(command, check=True, timeout=20, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        # Some desktops keep the launcher attached to the viewer: it may be open.
        return
    except (OSError, subprocess.CalledProcessError, RuntimeError):
        if shutil.which('notify-send'):
            subprocess.run(['notify-send', '-a', 'Screen Capture', 'File saved',
                            f'Could not open the default viewer. File: {path}'],
                           timeout=5, check=False)


def overlay_rectangles(monitor, selection=None):
    if selection is None:
        return [monitor]
    x, y, w, h = selection
    mx, my, mw, mh = monitor
    result = []
    for sx, sy, sw, sh in [(x-2, y-2, w+4, 2), (x-2, y+h, w+4, 2),
                            (x-2, y, 2, h), (x+w, y, 2, h)]:
        left, top = max(mx, sx), max(my, sy)
        right, bottom = min(mx+mw, sx+sw), min(my+mh, sy+sh)
        if right > left and bottom > top:
            result.append((left, top, right-left, bottom-top))
    return result


def show_overlay(outline=None):
    import gi
    gi.require_version('Gtk', '3.0')
    layer = None
    wayland = os.environ.get('XDG_SESSION_TYPE') == 'wayland' or (
        os.environ.get('XDG_SESSION_TYPE') not in ('x11', 'xorg') and os.environ.get('WAYLAND_DISPLAY'))
    if wayland:
        try:
            gi.require_version('GtkLayerShell', '0.1')
            from gi.repository import GtkLayerShell
            layer = GtkLayerShell
        except (ImportError, ValueError):
            pass
    # Gtk popup windows are override-redirect on X11, so they never tile or focus.
    # XWayland provides the same fallback if native layer-shell isn't installed.
    if layer:
        os.environ['GDK_BACKEND'] = 'wayland'
    elif os.environ.get('DISPLAY'):
        os.environ['GDK_BACKEND'] = 'x11'
    else:
        raise RuntimeError('Wayland flash requires gir1.2-gtklayershell-0.1')
    import ctypes
    from gi.repository import Gtk, Gdk, GLib
    Gtk.init([])
    display = Gdk.Display.get_default()
    if display is None:
        raise RuntimeError('No display for feedback')
    # Use the underlying GTK libraries to set an empty input region. This avoids
    # requiring the optional python3-gi-cairo foreign-type bridge.
    cairo = ctypes.CDLL('libcairo.so.2')
    cairo.cairo_region_create.restype = ctypes.c_void_p
    cairo.cairo_region_destroy.argtypes = [ctypes.c_void_p]
    gdk = ctypes.CDLL('libgdk-3.so.0')
    gdk.gdk_window_input_shape_combine_region.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    pointer = ctypes.pythonapi.PyCapsule_GetPointer
    pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    pointer.restype = ctypes.c_void_p
    windows = []
    began = None

    def make_clickthrough(window):
        region = cairo.cairo_region_create()
        gdk.gdk_window_input_shape_combine_region(pointer(window.get_window().__gpointer__, None), region, 0, 0)
        cairo.cairo_region_destroy(region)

    def mapped(window, event):
        nonlocal began
        if began is None:
            began = GLib.get_monotonic_time()
        return False

    provider = Gtk.CssProvider()
    provider.load_from_data(b'window { background-image: none; background-color: #f22633; }' if outline else
                            b'window { background-image: none; background-color: white; }')
    for index in range(display.get_n_monitors()):
        monitor = display.get_monitor(index)
        rect = monitor.get_geometry()
        for x, y, width, height in overlay_rectangles((rect.x, rect.y, rect.width, rect.height), outline):
            window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL if layer else Gtk.WindowType.POPUP)
            window.set_title('Recording Outline' if outline else 'Capture Flash')
            window.set_decorated(False)
            window.set_accept_focus(False)
            window.set_focus_on_map(False)
            window.set_skip_taskbar_hint(True)
            window.set_skip_pager_hint(True)
            window.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            window.set_opacity(1 if outline else 0.30)
            if layer:
                layer.init_for_window(window)
                layer.set_namespace(window, 'vicinae-capture-feedback')
                layer.set_layer(window, layer.Layer.OVERLAY)
                layer.set_monitor(window, monitor)
                layer.set_keyboard_mode(window, layer.KeyboardMode.NONE)
                layer.set_exclusive_zone(window, -1)
                layer.set_anchor(window, layer.Edge.TOP, True)
                layer.set_anchor(window, layer.Edge.LEFT, True)
                layer.set_margin(window, layer.Edge.TOP, y - rect.y)
                layer.set_margin(window, layer.Edge.LEFT, x - rect.x)
                window.set_default_size(width, height)
            else:
                window.set_keep_above(True)
                window.move(x, y)
                window.resize(width, height)
            window.connect('realize', make_clickthrough)
            window.connect('map-event', mapped)
            windows.append(window)
            window.show_all()

    if not windows:
        return

    def close_overlay():
        for window in windows:
            window.destroy()
        display.sync()
        Gtk.main_quit()
        return False

    if not outline:
        def tick():
            if began is not None:
                elapsed = (GLib.get_monotonic_time() - began) / 1000
                if elapsed >= 180:
                    return close_overlay()
                for window in windows:
                    window.set_opacity(0.30 * (1 - elapsed / 180))
            return True
        GLib.timeout_add(16, tick)
        GLib.timeout_add(1000, close_overlay)
    else:
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, close_overlay)
        parent = os.getppid()
        def check_parent():
            if os.getppid() != parent:
                return close_overlay()
            return True
        GLib.timeout_add(1000, check_parent)
    Gtk.main()


if __name__ == '__main__':
    if sys.argv[1:] == ['flash']:
        show_overlay()
    elif len(sys.argv) == 3 and sys.argv[1] == 'outline':
        match = re.fullmatch(r'(-?\d+),(-?\d+) (\d+)x(\d+)', sys.argv[2])
        if not match:
            raise SystemExit('Invalid outline rectangle')
        show_overlay(tuple(map(int, match.groups())))
    elif len(sys.argv) == 3 and sys.argv[1] == 'open':
        open_file(sys.argv[2])
