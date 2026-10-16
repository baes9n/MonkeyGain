"""MonkeyGain native GTK 4 desktop application."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk, Gdk, Pango

from . import __version__
from .desktop import APP_ID
from .core import (
    ScanRunner, ScanSettings, ScanMetric, probe_backend, discover_audio,
    make_album_jobs,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = PROJECT_DIR / 'assets'
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'monkeygain'
CONFIG_FILE = CONFIG_DIR / 'settings.json'


def elide(text: str, max_len: int = 80) -> str:
    return text if len(text) <= max_len else text[:max_len - 1] + '…'


def label(text: str, css: str = '', *, wrap: bool = False, xalign: float = 0) -> Gtk.Label:
    item = Gtk.Label(label=text, xalign=xalign)
    item.set_wrap(wrap)
    if css:
        item.add_css_class(css)
    return item


def button(text: str, icon: str, callback, css: str = '') -> Gtk.Button:
    b = Gtk.Button()
    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
    content.append(Gtk.Image.new_from_icon_name(icon))
    content.append(label(text))
    b.set_child(content)
    if css:
        b.add_css_class(css)
    b.connect('clicked', callback)
    return b


class MonkeyGainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application, title='MonkeyGain')
        self.set_default_size(1180, 780)
        self.set_size_request(800, 580)
        self._files: set[Path] = set()
        self._rows: list[dict] = []
        self._results: dict[Path, dict] = {}
        self._jobs = []
        self._busy = False
        self._settings = self._read_settings()
        self.backend = probe_backend(self._settings.get('backend_path', ''))
        self._runner = ScanRunner(
            lambda line: GLib.idle_add(self._append_log, line),
            lambda idx, status: GLib.idle_add(self._on_job, idx, status),
            lambda ok, err, canceled: GLib.idle_add(self._on_finished, ok, err, canceled),
            lambda idx, metric: GLib.idle_add(self._on_metric, idx, metric),
            lambda idx, track: GLib.idle_add(self._on_track, idx, track),
        )
        self.connect('close-request', self._on_close)
        self._init_css()
        self._create_widgets()
        self._set_appearance(self._settings.get('theme', 'dark'))
        self._append_log(f'MonkeyGain {__version__} · Ready to scan.\n')
        self._refresh_backend(log_failure=True)
        self._update_collection()

    @staticmethod
    def _read_settings() -> dict:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_settings(self, *_args):
        settings = {
            'album': self.album_switch.get_active(),
            'true_peak': self.true_peak_switch.get_active(),
            'loudness': self.loud_spin.get_value_as_int(),
            'max_peak': self.peak_spin.get_value(),
            'clip_mode': ('p', 'a', 'n')[self.clip_choice.get_selected()],
            'write_tags': self.write_switch.get_active(),
            'skip_existing': self.skip_switch.get_active(),
            'theme': ('system', 'light', 'dark')[self.theme_choice.get_selected()],
            'backend_path': self.backend_entry.get_text().strip(),
            'last_folder': self._settings.get('last_folder', ''),
            'notifications': self.notify_switch.get_active(),
        }
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
        except OSError:
            pass

    def _init_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_path(str(ASSET_DIR / 'style.css'))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _create_widgets(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        # Accept files and folders dropped anywhere on the main window.
        self._drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        self._drop_target.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._drop_target.connect('enter', self._drop_enter)
        self._drop_target.connect('leave', self._drop_leave)
        self._drop_target.connect('drop', self._on_drop)
        root.add_controller(self._drop_target)
        self._drop_surface = root

        header = Gtk.HeaderBar()
        header.add_css_class('mg-header')
        # Prevent Gtk.HeaderBar from adding its default centered window title.
        # The window manager still uses the actual window title, MonkeyGain.
        header.set_title_widget(Gtk.Box())
        self.add_folder_button = button('Add Folder', 'folder-open-symbolic', self._choose_folder)
        self.add_file_button = button('Add Files', 'list-add-symbolic', self._choose_files)
        self.clear_button = button('Clear', 'edit-clear-all-symbolic', self._clear)
        header.pack_start(self.add_folder_button)
        header.pack_start(self.add_file_button)
        header.pack_end(self.clear_button)
        root.append(header)

        content = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        content.set_wide_handle(False)
        content.set_position(700)
        content.set_resize_start_child(True)
        content.set_shrink_start_child(False)
        content.set_resize_end_child(False)
        content.set_shrink_end_child(False)
        content.set_vexpand(True)
        root.append(content)

        workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        workspace.set_margin_start(22)
        workspace.set_margin_end(18)
        workspace.set_margin_top(20)
        workspace.set_margin_bottom(12)
        content.set_start_child(workspace)

        overview = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        overview.set_valign(Gtk.Align.CENTER)
        headings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        headings.set_hexpand(True)
        headings.append(label('Your Library', 'mg-title'))
        headings.append(label('Import albums and analyze loudness without changing audio samples.', 'mg-description', wrap=True))
        overview.append(headings)
        self.count_label = label('0 albums · 0 tracks', 'mg-count')
        overview.append(self.count_label)
        workspace.append(overview)

        self.album_scroller = Gtk.ScrolledWindow()
        self.album_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.album_scroller.set_vexpand(True)
        self.album_scroller.add_css_class('mg-card')
        self.album_list = Gtk.ListBox()
        self.album_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.album_list.add_css_class('mg-album-list')
        self.album_list.set_placeholder(self._placeholder())
        self.album_scroller.set_child(self.album_list)
        workspace.append(self.album_scroller)

        logs_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        logs_header.append(label('Analysis Log', 'mg-section'))
        space = Gtk.Box()
        space.set_hexpand(True)
        logs_header.append(space)
        logs_header.append(button('Export', 'document-save-symbolic', self._export_log))
        workspace.append(logs_header)
        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_min_content_height(147)
        log_scroll.set_size_request(-1, 150)
        log_scroll.add_css_class('mg-log-card')
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.log_view.set_left_margin(12)
        self.log_view.set_right_margin(12)
        self.log_view.set_top_margin(10)
        self.log_view.set_bottom_margin(10)
        self.log_view.add_css_class('mg-log')
        log_scroll.set_child(self.log_view)
        workspace.append(log_scroll)

        sidebar_scroller = Gtk.ScrolledWindow()
        sidebar_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroller.set_size_request(300, -1)
        sidebar_scroller.add_css_class('mg-sidebar')
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)
        sidebar.set_margin_start(20)
        sidebar.set_margin_end(20)
        sidebar.set_margin_top(20)
        sidebar.set_margin_bottom(20)
        sidebar_scroller.set_child(sidebar)
        content.set_end_child(sidebar_scroller)
        sidebar.append(label('Settings', 'mg-title'))
        sidebar.append(label('Custom profile · rsgain custom', 'mg-description'))
        self.config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        sidebar.append(self.config_box)

        self.loud_spin = Gtk.SpinButton.new_with_range(-30, -5, 1)
        self.loud_spin.set_value(int(self._settings.get('loudness', -18)))
        self._field('Target Loudness', self.loud_spin, 'LUFS')
        self.peak_spin = Gtk.SpinButton.new_with_range(-20, 0, 0.5)
        self.peak_spin.set_digits(1)
        self.peak_spin.set_value(float(self._settings.get('max_peak', -1)))
        self._field('Maximum Peak', self.peak_spin, 'dB')
        self.clip_choice = Gtk.DropDown.new_from_strings([
            'Positive gain only', 'Always protect', 'No protection',
        ])
        clip = self._settings.get('clip_mode', 'p')
        self.clip_choice.set_selected({'p': 0, 'a': 1, 'n': 2}.get(clip, 0))
        self.config_box.append(self._plain_field('Clipping Protection', self.clip_choice))
        sidebar.append(Gtk.Separator())

        self.album_switch = self._switch('Album Gain', 'Calculate a shared gain for each folder',
                                         bool(self._settings.get('album', True)), sidebar)
        self.true_peak_switch = self._switch('True Peak', 'Detect inter-sample peaks',
                                             bool(self._settings.get('true_peak', True)), sidebar)
        self.write_switch = self._switch('Write Tags', 'Turn off to scan without writing metadata',
                                         bool(self._settings.get('write_tags', True)), sidebar)
        self.skip_switch = self._switch('Skip Existing Tags', 'Keep existing ReplayGain values',
                                        bool(self._settings.get('skip_existing', False)), sidebar)
        sidebar.append(Gtk.Separator())
        self.theme_choice = Gtk.DropDown.new_from_strings(['System', 'Light', 'Dark'])
        self.theme_choice.set_selected({'system': 0, 'light': 1, 'dark': 2}.get(
            self._settings.get('theme', 'dark'), 2))
        sidebar.append(self._plain_field('Appearance', self.theme_choice))
        self.notify_switch = self._switch('Desktop Notifications',
                                          'Notify when a scan finishes',
                                          bool(self._settings.get('notifications', True)), sidebar)
        sidebar.append(Gtk.Separator())
        sidebar.append(label('rsgain Executable', 'mg-field-label'))
        self.backend_entry = Gtk.Entry()
        self.backend_entry.set_text(self._settings.get('backend_path', ''))
        self.backend_entry.set_placeholder_text('Auto-detect')
        self.backend_entry.set_tooltip_text('Leave blank to search PATH and standard Linux locations.')
        sidebar.append(self.backend_entry)
        self.backend_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.backend_row.append(button('Browse…', 'document-open-symbolic', self._browse_backend))
        self.backend_row.append(button('Check', 'view-refresh-symbolic', self._check_backend))
        sidebar.append(self.backend_row)
        sidebar.append(label('Albums are grouped by folder. Do not mix separate albums in the same folder.',
                             'mg-hint', wrap=True))

        for control in (self.loud_spin, self.peak_spin):
            control.connect('value-changed', self._save_settings)
        for control in (self.album_switch, self.true_peak_switch, self.write_switch, self.skip_switch):
            control.connect('notify::active', self._save_settings)
        self.clip_choice.connect('notify::selected', self._save_settings)
        self.theme_choice.connect('notify::selected', self._theme_changed)
        self.notify_switch.connect('notify::active', self._save_settings)
        self.backend_entry.connect('changed', self._save_settings)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.set_margin_start(22)
        footer.set_margin_end(22)
        footer.set_margin_top(10)
        footer.set_margin_bottom(12)
        footer.add_css_class('mg-footer')
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_hexpand(True)
        self.status_label = label('Ready · Add files or folders', 'mg-description')
        status_box.append(self.status_label)
        self.engine_label = label('Checking rsgain…', 'mg-muted-small')
        status_box.append(self.engine_label)
        footer.append(status_box)
        self.progress = Gtk.ProgressBar()
        self.progress.set_size_request(170, -1)
        self.progress.set_valign(Gtk.Align.CENTER)
        self.progress.set_show_text(True)
        self.progress.set_fraction(0)
        self.progress.set_text('0% · albums')
        footer.append(self.progress)
        self.cancel_button = button('Cancel', 'process-stop-symbolic', self._cancel)
        self.cancel_button.set_sensitive(False)
        footer.append(self.cancel_button)
        self.run_button = button('Start Scan', 'media-playback-start-symbolic', self._confirm_start, 'mg-primary')
        footer.append(self.run_button)
        root.append(footer)

    def _placeholder(self) -> Gtk.Widget:
        block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        block.set_halign(Gtk.Align.CENTER)
        block.set_valign(Gtk.Align.CENTER)
        block.set_margin_top(65)
        block.set_margin_bottom(65)
        icon = Gtk.Image.new_from_icon_name('folder-music-symbolic')
        icon.set_pixel_size(54)
        icon.add_css_class('mg-muted')
        block.append(icon)
        block.append(label('Your music starts here', 'mg-section', xalign=0.5))
        block.append(label('Drop audio files or folders here, or use Add Files / Add Folder.',
                           'mg-description', xalign=0.5))
        return block

    def _plain_field(self, title: str, widget: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        box.append(label(title, 'mg-field-label'))
        box.append(widget)
        return box

    def _field(self, title: str, spin: Gtk.SpinButton, unit: str):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_box.set_hexpand(True)
        title_box.append(label(title, 'mg-field-label'))
        title_box.append(label(unit, 'mg-muted-small'))
        box.append(title_box)
        spin.set_width_chars(5)
        box.append(spin)
        self.config_box.append(box)

    def _switch(self, title: str, description: str, active: bool, container: Gtk.Box) -> Gtk.Switch:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        txt.set_hexpand(True)
        txt.append(label(title, 'mg-field-label'))
        txt.append(label(description, 'mg-muted-small', wrap=True))
        row.append(txt)
        control = Gtk.Switch()
        control.set_active(active)
        control.set_valign(Gtk.Align.CENTER)
        row.append(control)
        container.append(row)
        return control

    def _theme_changed(self, *_args):
        choice = ('system', 'light', 'dark')[self.theme_choice.get_selected()]
        self._set_appearance(choice)
        self._save_settings()

    def _set_appearance(self, mode: str):
        for name in ('mg-dark', 'mg-light'):
            self.remove_css_class(name)
        dark = mode == 'dark'
        if mode == 'system':
            try:
                schema = Gio.SettingsSchemaSource.get_default().lookup('org.gnome.desktop.interface', True)
                if schema and schema.has_key('color-scheme'):
                    dark = Gio.Settings.new('org.gnome.desktop.interface').get_string('color-scheme') == 'prefer-dark'
                else:
                    dark = False
            except Exception:
                dark = False
        self.add_css_class('mg-dark' if dark else 'mg-light')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', dark)

    def _refresh_backend(self, *, log_failure: bool = False):
        self.backend = probe_backend(self.backend_entry.get_text())
        for css in ('mg-ok', 'mg-error'):
            self.engine_label.remove_css_class(css)
        if self.backend.path:
            self.engine_label.set_text(f'rsgain {self.backend.version} · Ready' if self.backend.version != 'unknown' else 'rsgain · Ready')
            self.engine_label.set_tooltip_text(self.backend.path)
            self.engine_label.add_css_class('mg-ok')
            self._append_log(f'Engine detected: {self.backend.path} (version: {self.backend.version})\n')
        else:
            self.engine_label.set_text('rsgain unavailable · Check executable path')
            self.engine_label.set_tooltip_text(self.backend.error)
            self.engine_label.add_css_class('mg-error')
            if log_failure:
                self._append_log('Engine diagnostics:\n' + self.backend.error + '\n')
        if not self._runner.running:
            self.run_button.set_sensitive(bool(self._jobs) and bool(self.backend.path) and not self._busy)

    def _check_backend(self, *_args):
        self._save_settings()
        self._refresh_backend(log_failure=True)

    def _browse_backend(self, *_args):
        dialog = Gtk.FileDialog()
        dialog.set_title('Choose rsgain Executable')
        dialog.open(self, None, self._on_backend_selected)

    def _on_backend_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file.get_path():
                self.backend_entry.set_text(file.get_path())
                self._check_backend()
        except GLib.Error:
            return

    def _new_file_dialog(self, title: str) -> Gtk.FileDialog:
        dialog = Gtk.FileDialog()
        dialog.set_title(title)
        remembered = Path(self._settings.get('last_folder') or Path.home()).expanduser()
        if remembered.is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(str(remembered)))
        return dialog

    def _remember_folder(self, paths: list[str]) -> None:
        for raw in paths:
            path = Path(raw).expanduser()
            folder = path if path.is_dir() else path.parent
            if folder.is_dir():
                self._settings['last_folder'] = str(folder.resolve())
                self._save_settings()
                return

    def _drop_enter(self, _target, _x, _y):
        if self._busy or self._runner.running:
            return Gdk.DragAction(0)
        self._drop_surface.add_css_class('mg-drop-active')
        return Gdk.DragAction.COPY

    def _drop_leave(self, *_args):
        self._drop_surface.remove_css_class('mg-drop-active')

    def _on_drop(self, _target, value, _x, _y):
        self._drop_leave()
        if self._busy or self._runner.running or not isinstance(value, Gdk.FileList):
            return False
        paths = [file.get_path() for file in value.get_files()]
        local_paths = [path for path in paths if path]
        if not local_paths:
            self._append_log('Only local files and folders can be imported.\n')
            return False
        self._discover(local_paths)
        return True

    def _choose_files(self, *_args):
        dialog = self._new_file_dialog('Select Audio Files')
        dialog.open_multiple(self, None, self._on_files_selected)

    def _on_files_selected(self, dialog, result):
        try:
            model = dialog.open_multiple_finish(result)
            files = [model.get_item(n).get_path() for n in range(model.get_n_items())]
        except GLib.Error as exc:
            if not exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self._append_log(f'Could not select files: {exc}\n')
            return
        self._discover(files)

    def _choose_folder(self, *_args):
        dialog = self._new_file_dialog('Select Music Folder')
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error as exc:
            if not exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self._append_log(f'Could not select folder: {exc}\n')
            return
        self._discover([folder.get_path()])

    def _discover(self, files: list[str | None]):
        if self._busy:
            return
        paths = [path for path in files if path]
        if not paths:
            return
        self._busy = True
        self._set_import_sensitive(False)
        self._remember_folder(paths)
        self.status_label.set_text('Searching for supported audio files…')

        def task():
            try:
                result = discover_audio(paths)
                GLib.idle_add(self._on_discovered, result, '')
            except Exception as exc:
                GLib.idle_add(self._on_discovered, [], str(exc))
        threading.Thread(target=task, daemon=True).start()

    def _on_discovered(self, new_files: list[Path], error: str):
        self._busy = False
        self._set_import_sensitive(True)
        if error:
            self._append_log(f'Import error: {error}\n')
        old = len(self._files)
        self._files.update(new_files)
        self.status_label.set_text(f'{len(self._files) - old} new files added')
        if not new_files:
            self._append_log('No supported audio files were found.\n')
        self._update_collection()
        return GLib.SOURCE_REMOVE

    def _clear(self, *_args):
        if self._runner.running or self._busy:
            return
        self._files.clear()
        self._results.clear()
        self._update_collection()
        self.status_label.set_text('Queue cleared')

    def _remove_folder(self, _button, folder: Path):
        if self._runner.running or self._busy:
            return
        self._files = {file for file in self._files if file.parent != folder}
        self._results.pop(folder, None)
        self._update_collection()

    @staticmethod
    def _plural(number: int, singular: str, plural: str | None = None) -> str:
        return f'{number} {singular if number == 1 else (plural or singular + "s")}'

    @staticmethod
    def _fmt_number(number: float, unit: str = '', *, signed: bool = False) -> str:
        if number == float('-inf'):
            return '−∞' + (' ' + unit if unit else '')
        prefix = '+' if signed and number > 0 else ''
        return f'{prefix}{number:.2f}' + (' ' + unit if unit else '')

    def _make_album_row(self, job, position: int) -> dict:
        item = Gtk.ListBoxRow()
        item.add_css_class('mg-album-row')
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        item.set_child(wrapper)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class('mg-album-heading')
        toggle = Gtk.ToggleButton()
        toggle.set_active(position == 0)
        toggle.set_tooltip_text('Expand or collapse tracks')
        toggle.add_css_class('mg-expand-button')
        arrow = Gtk.Image.new_from_icon_name('pan-end-symbolic')
        toggle.set_child(arrow)
        header.append(toggle)

        album_art = Gtk.Box()
        album_art.add_css_class('mg-album-icon')
        art_icon = Gtk.Image.new_from_icon_name('media-optical-symbolic')
        art_icon.set_pixel_size(23)
        album_art.append(art_icon)
        header.append(album_art)

        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        titles.set_hexpand(True)
        title = label(job.label, 'mg-album-title')
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_tooltip_text(str(job.folder))
        titles.append(title)
        formats = ' / '.join(sorted({p.suffix[1:].upper() for p in job.files}))
        titles.append(label(f'{self._plural(len(job.files), "track")}  ·  {formats}', 'mg-muted-small'))
        header.append(titles)
        status_icon = Gtk.Image.new_from_icon_name('emblem-ok-symbolic')
        status_icon.set_visible(False)
        header.append(status_icon)
        status = label('Ready', 'mg-status')
        header.append(status)
        remove = Gtk.Button.new_from_icon_name('window-close-symbolic')
        remove.set_tooltip_text('Remove album from the queue')
        remove.add_css_class('flat')
        remove.connect('clicked', self._remove_folder, job.folder)
        header.append(remove)
        wrapper.append(header)

        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        revealer.set_transition_duration(160)
        revealer.set_reveal_child(position == 0)
        toggle.connect('toggled', lambda control: (
            revealer.set_reveal_child(control.get_active()),
            arrow.set_from_icon_name('pan-down-symbolic' if control.get_active() else 'pan-end-symbolic'),
        ))
        if position == 0:
            arrow.set_from_icon_name('pan-down-symbolic')
        wrapper.append(revealer)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        details.add_css_class('mg-details')
        revealer.set_child(details)

        album_stats = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        album_stats.add_css_class('mg-album-stats')
        stat_values = {}
        for title_text, key in [('ALBUM GAIN', 'gain'), ('LOUDNESS', 'loudness'), ('ALBUM PEAK', 'peak')]:
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            column.set_hexpand(True)
            column.append(label(title_text, 'mg-overline'))
            value = label('—', 'mg-stat-value')
            column.append(value)
            album_stats.append(column)
            stat_values[key] = value
        details.append(album_stats)

        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        columns.add_css_class('mg-track-columns')
        index_space = label('', 'mg-overline')
        index_space.set_width_chars(3)
        columns.append(index_space)
        track_title = label('TRACK', 'mg-overline')
        track_title.set_hexpand(True)
        columns.append(track_title)
        format_space = label('', 'mg-overline')
        format_space.set_width_chars(5)
        columns.append(format_space)
        for caption in ('LOUDNESS', 'GAIN', 'PEAK'):
            head = label(caption, 'mg-overline', xalign=1)
            head.set_width_chars(11)
            head.set_max_width_chars(11)
            columns.append(head)
        details.append(columns)

        track_widgets = {}
        for n, file in enumerate(job.files, start=1):
            track_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            track_row.add_css_class('mg-track-row')
            number = label(f'{n:02}', 'mg-track-index')
            number.set_width_chars(3)
            track_row.append(number)
            name = label(file.stem, 'mg-track-name')
            name.set_hexpand(True)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.set_tooltip_text(file.name)
            track_row.append(name)
            suffix = label(file.suffix[1:].upper(), 'mg-track-format')
            suffix.set_width_chars(5)
            track_row.append(suffix)
            values = {}
            for key in ('loudness', 'gain', 'peak'):
                value = label('—', 'mg-track-value', xalign=1)
                value.set_width_chars(11)
                value.set_max_width_chars(11)
                track_row.append(value)
                values[key] = value
            details.append(track_row)
            track_widgets[file.name] = {'values': values, 'row': track_row}
        self.album_list.append(item)
        return {
            'status': status, 'icon': status_icon, 'revealer': revealer,
            'toggle': toggle, 'stat_values': stat_values,
            'tracks': track_widgets, 'folder': job.folder,
        }

    def _apply_metrics(self, row: dict, result: dict) -> None:
        album: ScanMetric | None = result.get('album')
        stats = row['stat_values']
        stats['gain'].set_text(self._fmt_number(album.gain, 'dB', signed=True) if album else '—')
        stats['loudness'].set_text(self._fmt_number(album.loudness, 'LUFS') if album else '—')
        stats['peak'].set_text(self._fmt_number(album.peak_db, 'dBTP' if album.peak_type == 'True' else 'dBFS') if album else '—')
        for name, item in row['tracks'].items():
            metric: ScanMetric | None = result.get('tracks', {}).get(name)
            values = item['values']
            values['loudness'].set_text(self._fmt_number(metric.loudness) if metric else '—')
            values['gain'].set_text(self._fmt_number(metric.gain, 'dB', signed=True) if metric else '—')
            values['peak'].set_text(self._fmt_number(metric.peak_db, 'dB') if metric else '—')
            if metric:
                values['peak'].set_tooltip_text(f'{metric.peak_type} peak: {metric.peak:.6f} linear')
                if metric.clipping_adjusted:
                    values['gain'].set_tooltip_text('Gain reduced to prevent clipping')
                    values['gain'].add_css_class('mg-adjusted')

    def _update_collection(self):
        self._jobs = make_album_jobs(self._files)
        self._rows.clear()
        while row := self.album_list.get_row_at_index(0):
            self.album_list.remove(row)
        ntracks = sum(len(job.files) for job in self._jobs)
        self.count_label.set_text(f'{self._plural(len(self._jobs), "album")}  ·  {self._plural(ntracks, "track")}')
        for position, job in enumerate(self._jobs):
            row = self._make_album_row(job, position)
            self._apply_metrics(row, self._results.get(job.folder, {}))
            self._rows.append(row)
        if not self._runner.running:
            self.progress.set_fraction(0)
            self.progress.set_text('0% · albums')
            self.run_button.set_sensitive(bool(self._jobs) and bool(self.backend.path) and not self._busy)

    def _on_metric(self, index: int, metric: ScanMetric):
        if index >= len(self._jobs) or index >= len(self._rows):
            return GLib.SOURCE_REMOVE
        folder = self._jobs[index].folder
        result = self._results.setdefault(folder, {'tracks': {}, 'album': None})
        if metric.is_album:
            result['album'] = metric
        else:
            result['tracks'][metric.filename] = metric
        self._apply_metrics(self._rows[index], result)
        return GLib.SOURCE_REMOVE

    def _on_track(self, index: int, filename: str):
        if index >= len(self._rows):
            return GLib.SOURCE_REMOVE
        self.status_label.set_text(f'Scanning: {filename}  ·  {index + 1}/{len(self._rows)} albums')
        row = self._rows[index]
        for trackname, item in row['tracks'].items():
            if trackname == filename:
                item['row'].add_css_class('mg-active-track')
            else:
                item['row'].remove_css_class('mg-active-track')
        return GLib.SOURCE_REMOVE

    def _scan_settings(self) -> ScanSettings:
        return ScanSettings(
            album=self.album_switch.get_active(),
            true_peak=self.true_peak_switch.get_active(),
            loudness=self.loud_spin.get_value_as_int(),
            clip_mode=('p', 'a', 'n')[self.clip_choice.get_selected()],
            max_peak=self.peak_spin.get_value(),
            write_tags=self.write_switch.get_active(),
            skip_existing=self.skip_switch.get_active(),
        )

    def _confirm_start(self, *_args):
        if not self._jobs or self._runner.running or self._busy:
            return
        config = self._scan_settings()
        if not config.write_tags:
            self._start(config)
            return
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text='Write ReplayGain Tags?',
        )
        dialog.props.secondary_text = (
            f'rsgain will update metadata in {sum(len(j.files) for j in self._jobs)} '
            'audio files. The audio samples will not change, but tags will be modified. '
            'We recommend testing with a copy of an album first.'
        )
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Write Tags', Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.connect('response', self._confirm_response, config)
        dialog.present()

    def _confirm_response(self, dialog, response, config):
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            self._start(config)

    def _start(self, config: ScanSettings):
        self._save_settings()
        self.log_view.get_buffer().set_text('')
        self._results.clear()
        self._update_collection()
        for row in self._rows:
            row['status'].set_text('Queued')
            row['icon'].set_visible(False)
        self.progress.set_fraction(0)
        self.progress.set_text('0% · albums')
        self.run_button.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        self._set_import_sensitive(False)
        self.config_box.set_sensitive(False)
        for control in (self.album_switch, self.true_peak_switch, self.write_switch, self.skip_switch,
                        self.theme_choice, self.notify_switch, self.clip_choice,
                        self.backend_entry, self.backend_row):
            control.set_sensitive(False)
        self.status_label.set_text('Starting scan…')
        try:
            self._runner.start(list(self._jobs), config, self.backend.path or 'rsgain')
        except Exception as exc:
            self._append_log(f'Could not start scan: {exc}\n')
            self._on_finished(0, 1, False)

    def _set_import_sensitive(self, active: bool):
        self.add_folder_button.set_sensitive(active)
        self.add_file_button.set_sensitive(active)
        self.clear_button.set_sensitive(active)

    def _on_job(self, index: int, status: str):
        mapping = {
            'running': ('Scanning…', 'media-playback-start-symbolic'),
            'success': ('Completed', 'emblem-ok-symbolic'),
            'failed': ('Failed', 'dialog-error-symbolic'),
            'cancelled': ('Cancelled', 'process-stop-symbolic'),
        }
        if index >= len(self._rows):
            return GLib.SOURCE_REMOVE
        caption, icon_name = mapping.get(status, ('Queued', 'content-loading-symbolic'))
        row = self._rows[index]
        row['status'].set_text(caption)
        row['icon'].set_from_icon_name(icon_name)
        row['icon'].set_visible(True)
        if status == 'running':
            row['toggle'].set_active(True)
            self.status_label.set_text(f'Scanning album {index + 1}/{len(self._rows)}: {self._jobs[index].label}')
        else:
            for item in row['tracks'].values():
                item['row'].remove_css_class('mg-active-track')
            done = sum(x['status'].get_text() in ('Completed', 'Failed', 'Cancelled') for x in self._rows)
            self.progress.set_fraction(done / len(self._rows))
            self.progress.set_text(f'{done}/{len(self._rows)} albums')
        return GLib.SOURCE_REMOVE

    def _on_finished(self, success: int, errors: int, cancelled: bool):
        self.config_box.set_sensitive(True)
        for control in (self.album_switch, self.true_peak_switch, self.write_switch, self.skip_switch,
                        self.theme_choice, self.notify_switch, self.clip_choice,
                        self.backend_entry, self.backend_row):
            control.set_sensitive(True)
        self._set_import_sensitive(True)
        self.cancel_button.set_sensitive(False)
        self.run_button.set_sensitive(bool(self._jobs) and bool(self.backend.path))
        if cancelled:
            message = f'Scan cancelled · {self._plural(success, "album")} completed, {errors} failed'
            finished = sum(x['status'].get_text() in ('Completed', 'Failed', 'Cancelled') for x in self._rows)
            if self._rows:
                self.progress.set_fraction(finished / len(self._rows))
        else:
            message = f'Scan finished · {self._plural(success, "album")} completed, {errors} failed'
            self.progress.set_fraction(1)
            self.progress.set_text('Scan finished')
        self.status_label.set_text(message)
        self._append_log(f'\n{message}\n')
        if self.notify_switch.get_active():
            try:
                notice = Gio.Notification.new('MonkeyGain scan finished' if not cancelled
                                              else 'MonkeyGain scan cancelled')
                notice.set_body(message)
                self.get_application().send_notification('scan-finished', notice)
            except GLib.Error as exc:
                self._append_log(f'Notification unavailable: {exc}\n')
        return GLib.SOURCE_REMOVE

    def _cancel(self, *_args):
        self.status_label.set_text('Cancelling scan…')
        self._runner.cancel()
        self.cancel_button.set_sensitive(False)

    def _append_log(self, message: str):
        buffer = self.log_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), message)
        end = buffer.get_end_iter()
        self.log_view.scroll_to_iter(end, 0, False, 0.0, 0.0)
        return GLib.SOURCE_REMOVE

    def _export_log(self, *_args):
        dialog = Gtk.FileDialog()
        dialog.set_title('Save Analysis Log')
        dialog.set_initial_name('monkeygain-log.txt')
        dialog.save(self, None, self._on_log_saved)

    def _on_log_saved(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            path = file.get_path()
            if not path:
                raise OSError('Choose a local destination.')
            buffer = self.log_view.get_buffer()
            text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            Path(path).write_text(text, encoding='utf-8')
            self.status_label.set_text('Log exported successfully')
        except GLib.Error:
            return
        except OSError as exc:
            self._append_log(f'Could not export log: {exc}\n')

    def _on_close(self, *_args):
        if self._runner.running:
            self._runner.cancel()
        return False


class MonkeyGain(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_activate(self):
        window = self.props.active_window
        if not window:
            window = MonkeyGainWindow(self)
        window.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        window = self.props.active_window
        if window:
            window._discover([f.get_path() for f in files if f.get_path()])


def main() -> int:
    return MonkeyGain().run(None)
