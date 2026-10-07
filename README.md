# vicinae-screencapture

Use **Screenshot** or **Record Video** in Vicinae. Bind **Print** to **Screen Capture** for a horizontal Screenshot / Screencast chooser. Use Left/Right and Enter to select; Escape goes back. Each entry opens directly with its capture options: an area, a window, the active window, or the current monitor. Screenshots also support all monitors. Press Enter to capture; Escape cancels area/window selection.

Screenshots default to **clipboard only**. The Destination option also offers save-and-copy and save-only. PNGs go to `Screenshots` inside the XDG Pictures directory. Recording defaults to area selection and GIF-only output in `~/Videos/Screencasts/` (using the XDG Videos directory). MP4 and MP4+GIF are also available in Format.

GIF-only output is silent and removes the temporary MP4 after successful export. MP4 modes offer no audio (default), system audio, or the default microphone. GIF export creates a silent, 15 fps GIF up to 1280 pixels wide. MP4+GIF mode preserves both files. The delay starts after selecting the capture area.

## Installation

Requires Node.js 22 or newer, npm, Python 3, and Vicinae. Install the capture tools for your session as listed below, then:

```sh
git clone https://github.com/masterpiece911/vicinae-screencapture.git
cd vicinae-screencapture
npm ci
npm run build
```

Search Vicinae for **Screen Capture**, **Screenshot**, **Record Video**, or **Stop Screen Recording**. Building installs the extension; no server restart is needed.

## Shortcuts

Optional Sway configuration (replace any existing Print bindings):

```sway
bindsym --release Print exec vicinae cmd launch @masterpiece/screen-capture:chooser
# Optional dedicated media button (XF86AudioMedia):
bindsym --release --no-repeat XF86AudioMedia exec vicinae cmd launch @masterpiece/screen-capture:chooser
# Direct supervisor control works without focusing/opening Vicinae.
bindsym --no-repeat --inhibited Mod4+XF86AudioMedia exec python3 ~/.local/share/vicinae/extensions/screen-capture/assets/capture.py stop
bindsym --to-code --no-repeat --inhibited Mod4+Print exec python3 ~/.local/share/vicinae/extensions/screen-capture/assets/capture.py stop
bindsym --to-code --no-repeat --inhibited Ctrl+Shift+Print exec python3 ~/.local/share/vicinae/extensions/screen-capture/assets/capture.py stop
bindsym --release Shift+Print exec python3 ~/.local/share/vicinae/extensions/screen-capture/assets/capture.py screenshot --target screen --destination copy
bindsym --release Shift+Alt+Print exec python3 ~/.local/share/vicinae/extensions/screen-capture/assets/capture.py screenshot --target area --destination copy
```


| Shortcut | Action |
| --- | --- |
| Print or media button (`XF86AudioMedia`) | Open horizontal Screenshot / Screencast chooser |
| Super+media button, Super+Print, or Ctrl+Shift+Print | Stop and save recording globally |
| Shift+Print | Copy all monitors using grimshot |
| Shift+Alt+Print | Select an area and copy using grimshot |

Repeat the stop bindings inside any Sway binding modes (such as `mode "resize"`) where you want them available. `--inhibited` keeps them active when remote-desktop/VM apps request shortcut pass-through. Super+Print is the primary stop shortcut; Ctrl+Shift+Print remains an alternative.

You can also search for **Screenshot**, **Record Video**, or **Stop Screen Recording** in Vicinae. A notification announces recording start and completion. Reopening Record Video shows recording state and elapsed time.

Wayland video is restricted to one monitor; Xorg can also record a region spanning monitors. Window capture records a fixed rectangle, not a tracked window: keep the window in place and unobscured. Audio modes are alternatives; simultaneous microphone and system audio mixing is not included. GIF conversion runs after recording stops. MP4 remains available if conversion fails. Recording logs are in `$XDG_RUNTIME_DIR/vicinae-screen-capture/recorder.log`.

## Implementation

Session detection first uses `XDG_SESSION_TYPE`, then falls back to `WAYLAND_DISPLAY` and `DISPLAY`. A Wayland desktop with XWayland's `DISPLAY` still uses the Wayland backend. With no graphical session, capture reports an error.

| Function | Wayland (Sway) | Xorg/X11 |
| --- | --- | --- |
| Screenshot | grimshot / grim | maim |
| Area/window selection | slurp | slop |
| Recording | wf-recorder | FFmpeg x11grab |
| Clipboard | wl-copy | xclip |
| Window/monitor geometry | swaymsg | xdotool, xrandr, xwininfo |

A detached Python supervisor manages recording, GIF export, notifications, and a private runtime control socket. The stop command signals only the recorder child owned by that supervisor. A lock prevents concurrent recordings. Clipboard contents are updated only after valid PNG data is available.

Built against Vicinae API 0.28.2. Python 3 uses only its standard library. Only tools needed for the selected backend/action are checked.

Wayland requires Sway, `grimshot`, `grim`, `slurp`, `jq`, `wl-copy`, `wf-recorder`, `ffmpeg`, and `notify-send`. This backend is for Sway/wlroots, not GNOME's Wayland screenshot portal.

On Ubuntu, install Xorg tools with `sudo apt install maim slop xdotool xclip x11-utils x11-xserver-utils ffmpeg libnotify-bin`. System audio and microphone lookup support either `pactl` (PulseAudio or PipeWire's PulseAudio compatibility service) or `wpctl` (PipeWire). GIF-only needs no audio tools.

On Xorg, Current Monitor uses the active window's center, falling back to the pointer location. Partially off-screen windows are clipped to the desktop. The Vicinae commands work in either session; the example global shortcuts are for Sway only. On another desktop, assign its keyboard shortcuts to `vicinae cmd launch @masterpiece/screen-capture:chooser` and `vicinae cmd launch @masterpiece/screen-capture:stop`.

Capture interfaces follow [maim/slop](https://github.com/naelstrof/maim) and [FFmpeg's X11 input documentation](https://ffmpeg.org/ffmpeg-devices.html#x11grab).

## Development

Run `npm ci`, `npm run typecheck`, `npm test`, and `npm run build`. The build installs the extension into Vicinae's user extension directory. To build without installing, run `npm run build -- --out /absolute/path/to/output`.

## Capture feedback

Successful screenshots briefly flash the screen; clipboard-only captures flash too. Recording shows a red, click-through outline instead of flashing at the start. The outline is drawn outside the selected rectangle to keep it out of the recording; edges at the monitor boundary have no room for an outline. A full-monitor recording may therefore have no visible border. The screen flashes after a recording finishes successfully, before GIF conversion.

Saved PNGs, MP4s, and GIFs open with the default desktop application using `xdg-open` (or `gio open` when unavailable). Clipboard-only captures do not open a viewer. GIF-only mode opens only the final GIF; MP4+GIF opens each saved output. Viewer or overlay failures do not delete captures or prevent recording.

Visual feedback needs GTK 3 Python bindings (`python3-gi`, `gir1.2-gtk-3.0`). On Wayland, `gir1.2-gtklayershell-0.1` provides a native overlay. When unavailable, the overlay uses XWayland if `DISPLAY` is available. On Xorg a compositing window manager provides transparency. Install `xdg-utils` for default-app file opening.
