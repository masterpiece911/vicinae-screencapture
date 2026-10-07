.DEFAULT_GOAL := help
SHELL := /bin/sh

# System package installation currently supports Debian/Ubuntu.
# BACKEND=all installs both capture backends; wayland and x11 install only one.
BACKEND ?= all
NPM ?= npm
SUDO ?= sudo

COMMON_PACKAGES := nodejs npm python3 python3-gi gir1.2-gtk-3.0 ffmpeg libnotify-bin xdg-utils pulseaudio-utils
WAYLAND_PACKAGES := grimshot grim slurp sway jq wl-clipboard wf-recorder gir1.2-gtklayershell-0.1
X11_PACKAGES := maim slop xdotool xclip x11-utils x11-xserver-utils

.PHONY: help deps system-deps npm-deps check-node build install check

help:
	@printf '%s\n' \
	  'make deps                  Install apt system packages and locked npm dependencies' \
	  'make deps BACKEND=wayland   Install only the Sway/Wayland capture dependencies' \
	  'make deps BACKEND=x11       Install only the Xorg capture dependencies' \
	  'make system-deps           Install system packages only (Debian/Ubuntu; sudo)' \
	  'make npm-deps              Install locked npm dependencies when needed' \
	  'make check                 Run TypeScript checks and Python tests' \
	  'make build                 Build into dist/ without installing' \
	  'make install               Build and install into your Vicinae extensions directory' \
	  '' \
	  'Run make as your normal user; only system-deps uses sudo.' \
	  'Install Vicinae separately. Node.js 22+ is required.'

# Keep system installation ahead of npm even when the caller uses make -j.
deps:
	$(MAKE) system-deps BACKEND="$(BACKEND)"
	$(MAKE) npm-deps

system-deps:
	@command -v apt-get >/dev/null || { echo 'Automatic system dependencies require Debian/Ubuntu (apt-get). See README for tools to install manually.' >&2; exit 1; }
	@case "$(BACKEND)" in \
	  all) packages='$(COMMON_PACKAGES) $(WAYLAND_PACKAGES) $(X11_PACKAGES)' ;; \
	  wayland) packages='$(COMMON_PACKAGES) $(WAYLAND_PACKAGES)' ;; \
	  x11) packages='$(COMMON_PACKAGES) $(X11_PACKAGES)' ;; \
	  *) echo 'BACKEND must be all, wayland, or x11.' >&2; exit 1 ;; \
	esac; \
	$(SUDO) apt-get install --yes $$packages

check-node:
	@command -v node >/dev/null || { echo 'Node.js 22+ is required. Run make deps or install Node.js first.' >&2; exit 1; }
	@node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("Node.js 22+ is required; upgrade Node.js before continuing."); process.exit(1); }'
	@command -v $(NPM) >/dev/null || { echo 'npm is required.' >&2; exit 1; }

node_modules/.make-deps: package.json package-lock.json | check-node
	$(NPM) ci --no-audit --no-fund
	@touch "$@"

npm-deps: node_modules/.make-deps

check: npm-deps
	$(NPM) run typecheck
	PYTHONDONTWRITEBYTECODE=1 $(NPM) test

build: npm-deps
	$(NPM) run build -- --out "$(CURDIR)/dist"

# Let the Vicinae SDK choose the user's extension directory (including XDG paths).
install: npm-deps
	$(NPM) run build
