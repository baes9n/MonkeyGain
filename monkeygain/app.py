"""MonkeyGain native GTK 4 desktop application."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import sys
import time

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk, Gdk, Pango

from .activity import ActivityJournal, format_elapsed
from .desktop import APP_ID
from .startup import check_runtime
from .importer import (ImportRunner, ImportUpdate, PAGE_SIZE, TRACKS_PER_BATCH,
                       page_bounds, matches_tag_filter, matches_album, group_imported_paths)
from .selection import AlbumSelection, plan_scan, plan_result_reveal
from .metadata import (ExistingGain, TagRead, common_album_value,
                       linear_peak_db, load_existing_tags)
from .core import (
    ScanRunner, ScanSettings, ScanMetric, discover_audio,
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
    def __init__(self, application: Gtk.Application, backend):
        super().__init__(application=application, title='MonkeyGain')
        self.set_default_size(1180, 780)
        self.set_size_request(800, 580)
        self._files: set[Path] = set()
        self._rows: list[dict] = []  # Only rendered rows on the current page.
        self._visible_rows: dict[Path, dict] = {}
        self._filtered_jobs = []
        self._album_folders: set[Path] = set()
        self._page = 0
        self._job_status: dict[Path, str] = {}
        self._import_runner = ImportRunner(lambda update: GLib.idle_add(self._on_import_update, update))
        self._import_generation = 0
        self._import_pulse_timer = None
        self._import_started_at: float | None = None
        self._import_discovered = 0
        self._import_inspected = 0
        self._library_dirty = False
        self._library_update_timer = None
        self._search_timer = None
        self._results: dict[Path, dict] = {}
        self._existing_tags: dict[Path, TagRead] = {}
        self._expanded_albums: dict[Path, bool] = {}
        self._tag_generation = 0
        self._scan_wrote_tags = False
        self._scan_started_at: float | None = None
        self._scan_active_album: int | None = None
        self._scan_completed_albums = 0
        self._scan_cancel_requested = False
        self._scan_progress_timer: int | None = None
        self._follow_scan = True  # Suspend automatically when the user navigates.
        self._last_active_folder: Path | None = None
        self._rendered_page_key = None
        self._rendered_page_number = None
        self._activity_journal = ActivityJournal()
        self._jobs = []
        self._scan_jobs = []  # Stable snapshot for currently running ScanRunner callbacks.
        self._selection = AlbumSelection()
        self._busy = False
        self._settings = self._read_settings()
        self.backend = backend
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
        self._append_log('ReplayGain engine ready.\n')
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
        self.refresh_button = button('Refresh Tags', 'view-refresh-symbolic', self._refresh_tags)
        self.refresh_button.set_sensitive(False)
        header.pack_start(self.add_folder_button)
        header.pack_start(self.add_file_button)
        header.pack_end(self.clear_button)
        header.pack_end(self.refresh_button)
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
        headings.append(label('Scan Queue', 'mg-title'))
        headings.append(label('Import music, select albums, and scan ReplayGain.', 'mg-description', wrap=True))
        overview.append(headings)
        self.count_label = label('0 albums · 0 tracks', 'mg-count')
        overview.append(self.count_label)
        workspace.append(overview)

        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text('Find albums or tracks to select')
        self.search_entry.set_tooltip_text('Search the album list. Use Select Matches to add matching albums to your scan selection.')
        self.search_entry.set_hexpand(True)
        self.search_entry.connect('search-changed', self._on_search_changed)
        search_row.append(self.search_entry)
        self.tags_filter = Gtk.DropDown.new_from_strings([
            'All albums', 'Already tagged', 'Needs tags', 'Unreadable tags',
        ])
        self.tags_filter.set_tooltip_text('Show albums by ReplayGain tag status; select the matching albums with Select Matches.')
        self.tags_filter.connect('notify::selected', self._on_search_changed)
        search_row.append(self.tags_filter)
        self.filter_count = label('', 'mg-muted-small')
        search_row.append(self.filter_count)
        workspace.append(search_row)

        selection_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        selection_row.add_css_class('mg-selection-bar')
        self.select_matches_button = button('Select Matches', 'edit-select-all-symbolic',
                                            self._select_matches)
        self.select_matches_button.set_tooltip_text(
            'Select all albums matching the search and tag filters, including other pages.')
        selection_row.append(self.select_matches_button)
        self.clear_selection_button = button('Clear Selection', 'edit-clear-symbolic',
                                             self._clear_selection)
        selection_row.append(self.clear_selection_button)
        self.selection_label = label('0 albums selected', 'mg-selection-count')
        self.selection_label.set_hexpand(True)
        self.selection_label.set_halign(Gtk.Align.END)
        selection_row.append(self.selection_label)
        workspace.append(selection_row)

        self.album_scroller = Gtk.ScrolledWindow()
        self.album_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.album_scroller.set_vexpand(True)
        self.album_scroller.add_css_class('mg-card')
        self.album_list = Gtk.ListBox()
        self.album_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.album_list.add_css_class('mg-album-list')
        self.album_list.set_placeholder(self._placeholder())
        self.album_scroller.set_child(self.album_list)
        # Never fight the user's manual scrolling while a multi-album scan runs.
        scroll_events = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_events.connect('scroll', self._on_manual_scroll)
        self.album_scroller.add_controller(scroll_events)
        workspace.append(self.album_scroller)

        paging = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        paging.add_css_class('mg-page-bar')
        self.prev_page = button('Previous', 'go-previous-symbolic', lambda *_: self._switch_page(-1))
        paging.append(self.prev_page)
        self.page_label = label('Page 1 of 1', 'mg-muted-small', xalign=0.5)
        self.page_label.set_hexpand(True)
        paging.append(self.page_label)
        self.next_page = button('Next', 'go-next-symbolic', lambda *_: self._switch_page(+1))
        paging.append(self.next_page)
        workspace.append(paging)

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
        sidebar.append(label('Analysis Options', 'mg-title'))
        sidebar.append(label('Choose how to scan and update your music.', 'mg-description'))
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
        sidebar.append(label('Albums are grouped by folder. Keep separate albums in separate folders.',
                             'mg-hint', wrap=True))

        for control in (self.loud_spin, self.peak_spin):
            control.connect('value-changed', self._save_settings)
        for control in (self.album_switch, self.true_peak_switch, self.write_switch, self.skip_switch):
            control.connect('notify::active', self._save_settings)
        self.clip_choice.connect('notify::selected', self._save_settings)
        self.theme_choice.connect('notify::selected', self._theme_changed)
        self.notify_switch.connect('notify::active', self._save_settings)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.set_margin_start(22)
        footer.set_margin_end(22)
        footer.set_margin_top(10)
        footer.set_margin_bottom(12)
        footer.add_css_class('mg-footer')
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_hexpand(True)
        self.status_label = label('Ready · Add files or folders', 'mg-description')
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.status_label.set_max_width_chars(30)
        status_box.append(self.status_label)
        footer.append(status_box)
        self.progress = Gtk.ProgressBar()
        self.progress.set_size_request(210, -1)
        self.progress.set_valign(Gtk.Align.CENTER)
        self.progress.set_show_text(True)
        self.progress.set_fraction(0)
        self.progress.set_text('')
        self.progress.set_visible(False)
        footer.append(self.progress)
        self.cancel_button = button('Cancel', 'process-stop-symbolic', self._cancel_current)
        self.cancel_button.set_sensitive(False)
        footer.append(self.cancel_button)
        self.run_button = button('Scan Selected', 'media-playback-start-symbolic',
                                 lambda *_: self._confirm_start(False), 'mg-primary')
        self.run_button.set_tooltip_text('Analyze only checked albums, even when hidden by search or pagination.')
        footer.append(self.run_button)
        self.scan_all_button = button('Scan All', 'media-playback-start-symbolic',
                                      lambda *_: self._confirm_start(True))
        self.scan_all_button.set_tooltip_text('Analyze every imported album, ignoring selection and filters.')
        footer.append(self.scan_all_button)
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

    def _no_matches_placeholder(self) -> Gtk.Widget:
        block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        block.set_halign(Gtk.Align.CENTER)
        block.set_valign(Gtk.Align.CENTER)
        block.set_margin_top(65)
        block.set_margin_bottom(65)
        block.append(label('No matching albums', 'mg-section', xalign=0.5))
        block.append(label('Try a different artist, album or track name.',
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

    def _log_elapsed(self):
        if self._scan_started_at is None:
            return None
        return max(0, int(time.monotonic() - self._scan_started_at))

    def _append_activity(self, level: str, message: str, elapsed: int | None = None):
        """Save diagnostic events without a visible terminal-style console."""
        self._activity_journal.add(level, message, elapsed)
        return GLib.SOURCE_REMOVE

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
        if self._busy or self._runner.running:
            return
        paths = [path for path in files if path]
        if not paths:
            return
        self._busy = True
        self._import_generation += 1
        self._import_discovered = 0
        self._import_inspected = 0
        self._set_import_sensitive(False)
        self.run_button.set_sensitive(False)
        self.scan_all_button.set_sensitive(False)
        self._remember_folder(paths)
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self.progress.set_text('Discovering files…')
        self.cancel_button.set_sensitive(True)
        self._import_started_at = time.monotonic()
        self.status_label.set_text('Finding audio files…')
        if self._import_pulse_timer is not None:
            GLib.source_remove(self._import_pulse_timer)
        self._import_pulse_timer = GLib.timeout_add(120, self._pulse_import)
        try:
            self._import_runner.start(paths)
        except Exception as exc:
            self._end_import(f'Import could not start: {exc}')

    def _pulse_import(self):
        if not self._busy or self._import_started_at is None:
            self._import_pulse_timer = None
            return GLib.SOURCE_REMOVE
        if self._import_inspected == 0:
            self.progress.pulse()
        return GLib.SOURCE_CONTINUE

    def _cancel_import(self, *_args):
        self._import_runner.cancel()
        self.cancel_button.set_sensitive(False)
        self.status_label.set_text('Stopping import safely…')
        self.progress.set_text('Cancelling import…')

    def _schedule_library_refresh(self):
        if self._library_update_timer is None:
            self._library_update_timer = GLib.timeout_add(350, self._flush_library_refresh)

    def _flush_library_refresh(self):
        self._library_update_timer = None
        if self._library_dirty:
            self._library_dirty = False
            self._update_collection()
        return GLib.SOURCE_REMOVE

    def _on_import_update(self, update: ImportUpdate):
        if not self._busy:
            return GLib.SOURCE_REMOVE
        self._import_discovered = update.discovered
        self._import_inspected = update.inspected
        if update.phase == 'discovering':
            self.progress.set_text(f'{update.discovered:,} files found')
            self.status_label.set_text('Finding supported audio files…')
        elif update.phase == 'reading':
            if update.files:
                previous = len(self._files)
                self._files.update(update.files)
                self._existing_tags.update(update.readings or {})
                if len(self._files) > previous:
                    self._library_dirty = True
                    self._schedule_library_refresh()
            total = update.discovered
            if total:
                self.progress.set_fraction(min(1, update.inspected / total))
            self.progress.set_text(f'Importing {update.inspected:,}/{total:,} files')
            self.status_label.set_text('Reading existing ReplayGain tags…')
        elif update.phase in ('complete', 'cancelled', 'error'):
            # Keep successfully imported batches even if the user cancels.
            self._flush_library_refresh()
            if update.phase == 'complete':
                tagged = sum(bool(t.info.tagged) for t in self._existing_tags.values())
                message = f'Imported {update.inspected:,} files · {tagged:,} with ReplayGain tags'
            elif update.phase == 'cancelled':
                message = f'Import cancelled · {update.inspected:,} files retained'
            else:
                message = f'Import error: {update.message}'
                self._append_log(message + '\n')
            self._end_import(message)
        return GLib.SOURCE_REMOVE

    def _end_import(self, message: str):
        self._busy = False
        self._import_started_at = None
        if self._import_pulse_timer is not None:
            GLib.source_remove(self._import_pulse_timer)
            self._import_pulse_timer = None
        self.cancel_button.set_sensitive(False)
        self.progress.set_text('Import finished' if 'Imported ' in message else 'Import stopped')
        if 'Imported ' in message:
            self.progress.set_fraction(1)
        self._set_import_sensitive(True)
        self._update_selection_ui()
        self.status_label.set_text(message)

    def _clear(self, *_args):
        if self._runner.running or self._busy:
            return
        self._tag_generation += 1
        self._files.clear()
        self._results.clear()
        self._existing_tags.clear()
        self._selection.clear()
        self._expanded_albums.clear()
        self._job_status.clear()
        self._page = 0
        self._update_collection()
        self.progress.set_visible(False)
        self.status_label.set_text('Queue cleared')

    def _remove_folder(self, _button, folder: Path):
        if self._runner.running or self._busy:
            return
        self._files = {file for file in self._files if file.parent != folder}
        self._results.pop(folder, None)
        self._selection.toggle(folder, False)
        self._expanded_albums.pop(folder, None)
        self._job_status.pop(folder, None)
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

    def _on_search_changed(self, *_args):
        if self._scan_started_at is not None:
            self._follow_scan = False
        # Debounce keyboard input, so a large library isn't searched on each key.
        if self._search_timer is not None:
            GLib.source_remove(self._search_timer)
        self._search_timer = GLib.timeout_add(180, self._search_now)

    def _search_now(self):
        self._search_timer = None
        self._page = 0
        self._apply_album_filter()
        return GLib.SOURCE_REMOVE

    def _apply_album_filter(self):
        query = self.search_entry.get_text().strip()
        tag_filter = self.tags_filter.get_selected()
        self._filtered_jobs = [job for job in self._jobs
            if (not query or matches_album(query, job.label, job.folder.parent.name,
                                          (file.stem for file in job.files)))
            and matches_tag_filter((self._existing_tags.get(path) for path in job.files),
                                   tag_filter)]
        total = len(self._filtered_jobs)
        self.filter_count.set_text(f'{total}/{len(self._jobs)} albums shown' if query or tag_filter else '')
        self.album_list.set_placeholder(
            self._no_matches_placeholder() if (query or tag_filter) else self._placeholder()
        )
        self._render_page()
        self._update_selection_ui()

    def _toggle_selection(self, folder: Path, active: bool):
        if self._busy or self._runner.running or self._scan_started_at is not None:
            return
        self._selection.toggle(folder, active)
        self._update_selection_ui()

    def _select_matches(self, *_args):
        if self._busy or self._runner.running:
            return
        self._selection.select(job.folder for job in self._filtered_jobs)
        for row in self._rows:
            row['checkbox'].set_active(True)
        self._update_selection_ui()

    def _clear_selection(self, *_args):
        if self._busy or self._runner.running:
            return
        self._selection.clear()
        for row in self._rows:
            row['checkbox'].set_active(False)
        self._update_selection_ui()

    def _update_selection_ui(self):
        count = self._selection.count()
        self.selection_label.set_text(f'{count:,} of {len(self._jobs):,} albums selected')
        active = (not self._busy and not self._runner.running
                  and self._scan_started_at is None)
        self.clear_selection_button.set_sensitive(active and count > 0)
        self.select_matches_button.set_sensitive(active and bool(self._filtered_jobs))
        can_scan = active and bool(self.backend.path)
        self.run_button.set_sensitive(can_scan and count > 0)
        self.scan_all_button.set_sensitive(can_scan and bool(self._jobs))

    def _on_manual_scroll(self, *_args):
        if self._scan_started_at is not None:
            self._follow_scan = False
        return False

    def _switch_page(self, delta: int):
        if self._scan_started_at is not None:
            self._follow_scan = False
        self._page += delta
        self._render_page()

    def _render_page(self):
        """Reuse unchanged rows so scans never reset expanded results or scroll."""
        total = len(self._filtered_jobs)
        self._page, start, end = page_bounds(total, self._page)
        n_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page_label.set_text(
            f'Page {self._page + 1} of {n_pages} · {start + 1 if total else 0}–{end} of {total} albums')
        self.prev_page.set_sensitive(self._page > 0)
        self.next_page.set_sensitive(end < total)
        key = tuple((job.folder, len(job.files)) for job in self._filtered_jobs[start:end])
        if (self._rendered_page_key == key and self._rendered_page_number == self._page):
            for row in self._rows:
                folder = row['folder']
                self._apply_metrics(row, self._results.get(folder, {}))
                if folder not in self._job_status or self._job_status[folder] == '':
                    self._tag_status(row)
                self._show_job_status(row, self._job_status.get(folder, ''))
            return
        old_page = self._rendered_page_number
        old_scroll = self.album_scroller.get_vadjustment().get_value()
        self._rendered_page_key = key
        self._rendered_page_number = self._page
        self._rows.clear()
        self._visible_rows.clear()
        while widget := self.album_list.get_row_at_index(0):
            self.album_list.remove(widget)
        for job in self._filtered_jobs[start:end]:
            row = self._make_album_row(job)
            self._visible_rows[job.folder] = row
            self._rows.append(row)
            self._apply_metrics(row, self._results.get(job.folder, {}))
            self._tag_status(row)
            self._show_job_status(row, self._job_status.get(job.folder, ''))
            if job.folder == self._last_active_folder:
                row['widget'].add_css_class('mg-scan-focus')
        # A deliberate page change starts at the top. For filtered refreshes on
        # the same page, restore the reader's position after GTK layout.
        target = old_scroll if old_page == self._page else 0
        GLib.idle_add(self._restore_album_scroll, target)

    def _restore_album_scroll(self, target: float):
        adjustment = self.album_scroller.get_vadjustment()
        maximum = max(adjustment.get_lower(), adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(min(max(adjustment.get_lower(), target), maximum))
        return GLib.SOURCE_REMOVE

    def _focus_active_album(self, folder: Path):
        """Follow a running album unless the user has manually navigated."""
        if not self._follow_scan:
            return
        index = next((n for n, job in enumerate(self._filtered_jobs)
                      if job.folder == folder), None)
        if index is None:  # Respect an active search/filter rather than clearing it.
            return
        page = index // PAGE_SIZE
        if page != self._page:
            self._page = page
            self._render_page()
        GLib.idle_add(self._scroll_to_active_album, folder)

    def _scroll_to_active_album(self, folder: Path):
        row = self._visible_rows.get(folder)
        if row is None or not self._follow_scan:
            return GLib.SOURCE_REMOVE
        try:
            ok, bounds = row['widget'].compute_bounds(self.album_list)
            if not ok:
                return GLib.SOURCE_REMOVE
            top = bounds.get_y() if hasattr(bounds, 'get_y') else bounds.origin.y
            height = bounds.get_height() if hasattr(bounds, 'get_height') else bounds.size.height
            adjustment = self.album_scroller.get_vadjustment()
            viewport_top = adjustment.get_value()
            viewport_bottom = viewport_top + adjustment.get_page_size()
            if top < viewport_top + 12:
                adjustment.set_value(max(adjustment.get_lower(), top - 12))
            elif top + height > viewport_bottom - 12:
                max_scroll = max(adjustment.get_lower(),
                                 adjustment.get_upper() - adjustment.get_page_size())
                adjustment.set_value(min(max_scroll,
                                         top + height - adjustment.get_page_size() + 12))
        except (AttributeError, TypeError, ValueError):
            # Scrolling assistance should never interrupt an audio scan.
            pass
        return GLib.SOURCE_REMOVE

    def _show_job_status(self, row: dict, current: str):
        captions = {
            'running': ('Scanning…', 'view-refresh-symbolic'),
            'success': ('Completed', 'emblem-ok-symbolic'),
            'failed': ('Failed', 'dialog-error-symbolic'),
            'cancelled': ('Cancelled', 'process-stop-symbolic'),
            'queued': ('Queued', None),
        }
        if current not in captions:
            return
        caption, icon_name = captions[current]
        row['status'].set_text(caption)
        if icon_name:
            row['icon'].set_from_icon_name(icon_name)
            row['icon'].set_visible(True)
        elif current == 'queued':
            row['icon'].set_visible(False)

    def _make_album_row(self, job) -> dict:
        item = Gtk.ListBoxRow()
        item.add_css_class('mg-album-row')
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        item.set_child(wrapper)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class('mg-album-heading')
        toggle = Gtk.ToggleButton()
        expanded = self._expanded_albums.get(job.folder, False)
        toggle.set_active(expanded)
        toggle.add_css_class('mg-expand-button')
        details_icon = Gtk.Image.new_from_icon_name('view-list-symbolic')
        # A list icon cannot be mistaken for a Play button.
        toggle_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        toggle_content.append(details_icon)
        toggle_caption = label('', 'mg-expand-caption')
        toggle_content.append(toggle_caption)
        toggle.set_child(toggle_content)
        header.append(toggle)

        # Compact icon only: never read embedded or external artwork.
        music_icon = Gtk.Image.new_from_icon_name('media-optical-symbolic')
        music_icon.set_pixel_size(17)
        music_icon.add_css_class('mg-muted')
        header.append(music_icon)

        album_checkbox = Gtk.CheckButton()
        album_checkbox.set_active(job.folder in self._selection.selected)
        album_checkbox.set_sensitive(not self._busy and self._scan_started_at is None
                                    and not self._runner.running)
        album_checkbox.set_tooltip_text('Include this album in Scan Selected')
        album_checkbox.connect('toggled', lambda control, folder=job.folder:
            self._toggle_selection(folder, control.get_active()))
        header.insert_child_after(album_checkbox, None)

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
        revealer.set_reveal_child(expanded)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        details.add_css_class('mg-details')
        revealer.set_child(details)
        wrapper.append(revealer)
        track_widgets = {}
        row = {
            'status': status, 'icon': status_icon, 'revealer': revealer,
            'toggle': toggle, 'widget': item, 'stat_values': {},
            'tracks': track_widgets, 'folder': job.folder, 'files': job.files,
            'checkbox': album_checkbox, 'details': details, 'built': False,
            'track_cursor': 0, 'expand_caption': toggle_caption,
        }
        def on_expanded(control):
            active = control.get_active()
            self._expanded_albums[job.folder] = active
            revealer.set_reveal_child(active)
            self._update_expander_caption(row)
            if active and not row['built']:
                self._build_track_details(row, job)
                self._apply_metrics(row, self._results.get(job.folder, {}))
        toggle.connect('toggled', on_expanded)
        self._update_expander_caption(row)
        self.album_list.append(item)
        if expanded:
            self._build_track_details(row, job)
        return row

    def _update_expander_caption(self, row: dict) -> None:
        """Make existing scan results easy to discover without building hidden rows."""
        result = self._results.get(row['folder'], {})
        has_results = bool(result.get('tracks') or result.get('album'))
        is_open = row['toggle'].get_active()
        caption = ('Hide results' if is_open else 'View results') if has_results else (
            'Hide tracks' if is_open else 'Show tracks')
        row['expand_caption'].set_text(caption)
        row['toggle'].set_tooltip_text(
            'Show album and per-track measurements' if has_results else 'Show tracks and existing ReplayGain tags')

    def _build_track_details(self, row: dict, job):
        """Create track widgets only for expanded, on-screen album cards."""
        if row['built']:
            return
        row['built'] = True
        details = row['details']
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

        row['stat_values'] = stat_values
        self._add_more_tracks(row, job)

    def _add_more_tracks(self, row: dict, job):
        """Only render up to TRACKS_PER_BATCH tracks per expansion action."""
        details = row['details']
        more = row.get('more_button')
        if more is not None:
            details.remove(more)
            row['more_button'] = None
        start = row['track_cursor']
        end = min(start + TRACKS_PER_BATCH, len(job.files))
        for n in range(start, end):
            file = job.files[n]
            track_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            track_row.add_css_class('mg-track-row')
            number = label(f'{n + 1:02}', 'mg-track-index')
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
            row['tracks'][file.name] = {'values': values, 'row': track_row,
                                        'title': name, 'file': file}
        row['track_cursor'] = end
        if end < len(job.files):
            more = button(f'Show next {min(TRACKS_PER_BATCH, len(job.files) - end)} tracks',
                          'go-down-symbolic',
                          lambda *_: self._show_more_tracks(row, job))
            more.add_css_class('mg-load-more')
            details.append(more)
            row['more_button'] = more
        self._apply_metrics(row, self._results.get(job.folder, {}))

    def _show_more_tracks(self, row, job):
        self._add_more_tracks(row, job)

    def _tag_status(self, row: dict) -> None:
        readings = [self._existing_tags.get(path) for path in row['files']]
        tagged = sum(bool(info and info.info.tagged) for info in readings)
        unknown = sum(bool(info and info.error) for info in readings)
        count = len(readings)
        if tagged == count and count:
            caption = 'Already tagged'
        elif tagged:
            caption = f'{tagged}/{count} tagged'
        elif unknown:
            caption = 'Tags unknown' if unknown == count else 'Partly unknown'
        else:
            caption = 'Not tagged'
        row['status'].set_text(caption)
        row['status'].set_tooltip_text(
            f'{tagged} files contain recognized ReplayGain/R128 tags, '
            f'{unknown} could not be inspected, {count - tagged - unknown} untagged.'
        )
        row['icon'].set_visible(bool(tagged))

    def _apply_metrics(self, row: dict, result: dict) -> None:
        """Fresh scan measurements take priority over stored metadata.

        Existing ReplayGain tags do not contain a measured LUFS figure or
        enough information to label peaks as true peaks: never invent either.
        """
        album: ScanMetric | None = result.get('album')
        stats = row['stat_values']
        if not stats:
            return
        readings = [self._existing_tags.get(path, TagRead()).info for path in row['files']]
        album_gain, gain_mixed = common_album_value(tag.album_gain for tag in readings)
        album_peak, peak_mixed = common_album_value(tag.album_peak for tag in readings)
        album_r128, r128_mixed = common_album_value(tag.r128_album_gain for tag in readings)
        for item in stats.values():
            item.set_tooltip_text(None)
        if album:
            stats['gain'].set_text(self._fmt_number(album.gain, 'dB', signed=True))
            stats['loudness'].set_text(self._fmt_number(album.loudness, 'LUFS'))
            stats['peak'].set_text(self._fmt_number(album.peak_db,
                'dBTP' if album.peak_type == 'True' else 'dBFS'))
            for item in stats.values():
                item.set_tooltip_text('Measured in the current scan')
        else:
            if gain_mixed or (r128_mixed and album_gain is None):
                stats['gain'].set_text('Mixed')
                stats['gain'].set_tooltip_text('Files contain conflicting album gain tags')
            elif album_gain is not None:
                stats['gain'].set_text(self._fmt_number(album_gain, 'dB', signed=True))
                stats['gain'].set_tooltip_text('Existing REPLAYGAIN_ALBUM_GAIN tag (not a new scan)')
            elif album_r128 is not None:
                stats['gain'].set_text(self._fmt_number(album_r128, 'dB', signed=True))
                stats['gain'].set_tooltip_text('Existing Opus R128 album gain; reference -23 LUFS, not ReplayGain target')
            else:
                stats['gain'].set_text('—')
            stats['loudness'].set_text('—')
            stats['loudness'].set_tooltip_text('Integrated LUFS is not stored in standard ReplayGain tags; run a scan to measure it')
            if peak_mixed:
                stats['peak'].set_text('Mixed')
                stats['peak'].set_tooltip_text('Files contain conflicting album peak tags')
            elif album_peak is not None:
                stats['peak'].set_text(self._fmt_number(linear_peak_db(album_peak), 'dB'))
                stats['peak'].set_tooltip_text('Existing ReplayGain album peak; true/sample peak type is unknown')
            else:
                stats['peak'].set_text('—')

        for name, item in row['tracks'].items():
            metric: ScanMetric | None = result.get('tracks', {}).get(name)
            reading = self._existing_tags.get(item['file'], TagRead())
            tag = reading.info
            values = item['values']
            item['title'].set_text(('✓  ' if tag.tagged else '') + item['file'].stem)
            item['title'].set_tooltip_text(
                f'{item["file"].name}\nExisting gain tags detected' if tag.tagged
                else (f'{item["file"].name}\nTag read error: {reading.error}' if reading.error
                      else f'{item["file"].name}\nNo existing gain tags detected')
            )
            if tag.tagged:
                item['title'].add_css_class('mg-tagged-name')
            else:
                item['title'].remove_css_class('mg-tagged-name')
            values['gain'].remove_css_class('mg-adjusted')
            for value in values.values():
                value.set_tooltip_text(None)
            if metric:
                values['loudness'].set_text(self._fmt_number(metric.loudness))
                values['gain'].set_text(self._fmt_number(metric.gain, 'dB', signed=True))
                values['peak'].set_text(self._fmt_number(metric.peak_db, 'dB'))
                values['peak'].set_tooltip_text(f'{metric.peak_type} peak: {metric.peak:.6f} linear, current scan')
                if metric.clipping_adjusted:
                    values['gain'].set_tooltip_text('Gain reduced to prevent clipping')
                    values['gain'].add_css_class('mg-adjusted')
            else:
                values['loudness'].set_text('—')
                values['loudness'].set_tooltip_text('Run a scan to measure loudness; LUFS is not in ReplayGain tags')
                gain = tag.track_gain if tag.track_gain is not None else tag.r128_track_gain
                values['gain'].set_text(self._fmt_number(gain, 'dB', signed=True) if gain is not None else '—')
                if tag.track_gain is not None:
                    values['gain'].set_tooltip_text('Existing REPLAYGAIN_TRACK_GAIN tag (not a new scan)')
                elif tag.r128_track_gain is not None:
                    values['gain'].set_tooltip_text('Existing Opus R128 track gain, reference -23 LUFS; not a ReplayGain -18 LUFS result')
                values['peak'].set_text(self._fmt_number(linear_peak_db(tag.track_peak), 'dB')
                                        if tag.track_peak is not None else '—')
                if tag.track_peak is not None:
                    values['peak'].set_tooltip_text('Existing linear ReplayGain peak converted to dB; sample/true peak type unknown')

    def _update_collection(self):
        self._jobs = group_imported_paths(self._files)
        self._album_folders = {job.folder for job in self._jobs}
        self._selection.prune(self._album_folders)
        self.refresh_button.set_sensitive(bool(self._files) and not self._busy and not self._runner.running)
        self.count_label.set_text(f'{self._plural(len(self._jobs), "album")}  ·  '
                                  f'{self._plural(len(self._files), "track")}')
        self._apply_album_filter()
        if not self._runner.running and not self._busy and self._scan_started_at is None:
            if not self._files:
                self.progress.set_visible(False)
        self._update_selection_ui()

    def _on_metric(self, index: int, metric: ScanMetric):
        if index >= len(self._scan_jobs):
            return GLib.SOURCE_REMOVE
        folder = self._scan_jobs[index].folder
        result = self._results.setdefault(folder, {'tracks': {}, 'album': None})
        if metric.is_album:
            result['album'] = metric
        else:
            result['tracks'][metric.filename] = metric
        if folder in self._visible_rows:
            row = self._visible_rows[folder]
            self._update_expander_caption(row)
            self._apply_metrics(row, result)
        return GLib.SOURCE_REMOVE

    def _on_track(self, index: int, filename: str):
        if index >= len(self._scan_jobs):
            return GLib.SOURCE_REMOVE
        self.status_label.set_text(f'Scanning: {filename}  ·  {index + 1}/{len(self._scan_jobs)} albums')
        row = self._visible_rows.get(self._scan_jobs[index].folder)
        if not row:
            return GLib.SOURCE_REMOVE
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

    def _confirm_start(self, all_albums: bool):
        if self._runner.running or self._busy or self._scan_started_at is not None:
            return
        jobs = plan_scan(self._jobs, self._selection.selected, all_albums=all_albums)
        if not jobs or not self.backend.path:
            self.status_label.set_text('Select at least one album, or use Scan All')
            return
        config = self._scan_settings()
        if not config.write_tags:
            self._start(config, jobs)
            return
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text='Write ReplayGain Tags?',
        )
        dialog.props.secondary_text = (
            f'rsgain will update metadata in {sum(len(j.files) for j in jobs)} '
            f'audio files across {len(jobs)} albums. '
            'Audio samples will not change, but tags will be modified. '
            'We recommend testing with a copy of an album first.'
        )
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Write Tags', Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.connect('response', self._confirm_response, config, tuple(jobs))
        dialog.present()

    def _confirm_response(self, dialog, response, config, jobs):
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            # Selection changes, clearing or re-importing are guarded while
            # the confirmation is open by the stable frozen tuple of jobs.
            self._start(config, list(jobs))

    def _start(self, config: ScanSettings, jobs):
        if self._runner.running or self._busy or self._scan_started_at is not None or not jobs:
            return
        self._scan_jobs = list(jobs)
        self._save_settings()
        self._scan_wrote_tags = config.write_tags
        self._activity_journal.clear()
        self._append_activity('info',
            f'Started scan queue · {self._plural(len(self._scan_jobs), "album")} · '
            f'{self._plural(sum(len(job.files) for job in self._scan_jobs), "track")}', 0)
        # Update the existing GTK row widgets in place. Never re-render the
        # entire album list when a scan begins: that used to reset its scroll.
        for job in self._scan_jobs:
            self._results.pop(job.folder, None)
            self._job_status[job.folder] = 'queued'
            row = self._visible_rows.get(job.folder)
            if row:
                self._apply_metrics(row, {})
                self._update_expander_caption(row)
                self._show_job_status(row, 'queued')
        for row in self._rows:
            row['widget'].remove_css_class('mg-scan-focus')
        self._follow_scan = True
        self._last_active_folder = None
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self.progress.set_text(f'0/{len(self._scan_jobs)} albums · 0:00')
        self._scan_started_at = time.monotonic()
        self._scan_active_album = None
        self._scan_completed_albums = 0
        self._scan_cancel_requested = False
        self.status_label.set_text('Starting scan…')
        if self._scan_progress_timer is not None:
            GLib.source_remove(self._scan_progress_timer)
        self._scan_progress_timer = GLib.timeout_add(250, self._tick_scan_progress)
        self.progress.pulse()
        self.run_button.set_sensitive(False)
        self.scan_all_button.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        self._set_import_sensitive(False)
        self.config_box.set_sensitive(False)
        for control in (self.album_switch, self.true_peak_switch, self.write_switch, self.skip_switch,
                        self.theme_choice, self.notify_switch, self.clip_choice):
            control.set_sensitive(False)
        self.status_label.set_text('Starting scan…')
        self.status_label.set_tooltip_text(None)
        try:
            self._runner.start(list(self._scan_jobs), config, self.backend.path or 'rsgain')
        except Exception as exc:
            self._append_log(f'Could not start scan: {exc}\n')
            self._on_finished(0, 1, False)

    def _set_import_sensitive(self, active: bool):
        self.add_folder_button.set_sensitive(active)
        self.add_file_button.set_sensitive(active)
        self.clear_button.set_sensitive(active)
        self.refresh_button.set_sensitive(active and bool(self._files))
        for row in self._rows:
            row['checkbox'].set_sensitive(active)
        self._update_selection_ui()

    def _tick_scan_progress(self):
        """One progress area, with genuine album counts and elapsed time.

        rsgain 3.4 TSV output has no trustworthy per-track percentage.
        An animated pulse indicates an active subprocess, not estimated work.
        """
        if self._scan_started_at is None:
            self._scan_progress_timer = None
            return GLib.SOURCE_REMOVE
        elapsed = format_elapsed(time.monotonic() - self._scan_started_at)
        total = len(self._scan_jobs)
        self.progress.set_text(f'{self._scan_completed_albums}/{total} albums')
        self.progress.pulse()
        if self._scan_active_album is not None and not self._scan_cancel_requested:
            i = self._scan_active_album
            self.status_label.set_text(
                f'Analyzing {self._scan_jobs[i].label} · album {i + 1}/{total} · {elapsed}'
            )
        return GLib.SOURCE_CONTINUE

    def _on_job(self, index: int, status: str):
        if index >= len(self._scan_jobs):
            return GLib.SOURCE_REMOVE
        job = self._scan_jobs[index]
        self._job_status[job.folder] = status
        row = self._visible_rows.get(job.folder)
        if row:
            self._show_job_status(row, status)
        if status == 'running':
            if self._last_active_folder in self._visible_rows:
                self._visible_rows[self._last_active_folder]['widget'].remove_css_class('mg-scan-focus')
            self._last_active_folder = job.folder
            self._scan_active_album = index
            self._focus_active_album(job.folder)
            row = self._visible_rows.get(job.folder)
            if row:
                row['widget'].add_css_class('mg-scan-focus')
            self.status_label.set_text(f'Scanning album {index + 1}/{len(self._scan_jobs)}: {job.label}')
            self._append_activity('working',
                f'Analyzing album {index + 1}/{len(self._scan_jobs)} · {job.label} '
                f'({self._plural(len(job.files), "track")})', self._log_elapsed())
        else:
            self._scan_active_album = None
            if status == 'success':
                result = self._results.get(job.folder, {})
                album = result.get('album')
                extra = (f' · {album.loudness:.2f} LUFS · '
                         f'{album.gain:+.2f} dB Album Gain') if album else ''
                num_metrics = len(result.get('tracks', {}))
                details = (f'{self._plural(num_metrics, "track")} reported' if num_metrics
                           else 'no track results in output')
                self._append_activity('success',
                    f'Completed {job.label} · {details}{extra}', self._log_elapsed())
            elif status == 'failed':
                self._append_activity('error',
                    f'Failed to analyze {job.label} · See the scan status for details', self._log_elapsed())
            elif status == 'cancelled':
                self._append_activity('warning',
                    f'Cancelled {job.label}', self._log_elapsed())
            if row:
                for item in row['tracks'].values():
                    item['row'].remove_css_class('mg-active-track')
            self._scan_completed_albums = sum(
                self._job_status.get(scanned.folder) in ('success', 'failed', 'cancelled')
                for scanned in self._scan_jobs)
            self.progress.set_fraction(self._scan_completed_albums / len(self._scan_jobs))
            self.progress.set_text(f'{self._scan_completed_albums}/{len(self._scan_jobs)} albums')
        return GLib.SOURCE_REMOVE

    def _on_finished(self, success: int, errors: int, cancelled: bool):
        elapsed_final = self._log_elapsed()
        self._scan_started_at = None
        self._scan_active_album = None
        if self._scan_progress_timer is not None:
            GLib.source_remove(self._scan_progress_timer)
            self._scan_progress_timer = None
        self.config_box.set_sensitive(True)
        for control in (self.album_switch, self.true_peak_switch, self.write_switch, self.skip_switch,
                        self.theme_choice, self.notify_switch, self.clip_choice):
            control.set_sensitive(True)
        self._set_import_sensitive(True)
        self.cancel_button.set_sensitive(False)
        self._update_selection_ui()
        if cancelled:
            message = f'Scan cancelled · {self._plural(success, "album")} completed, {errors} failed'
            finished = sum(
                self._job_status.get(scanned.folder) in ('success', 'failed', 'cancelled')
                for scanned in self._scan_jobs)
            if self._scan_jobs:
                self.progress.set_fraction(finished / len(self._scan_jobs))
        else:
            message = f'Scan finished · {self._plural(success, "album")} completed, {errors} failed'
            self.progress.set_fraction(1)
            self.progress.set_text('Scan finished')
        if elapsed_final is not None:
            message += f' · {format_elapsed(elapsed_final)}'
        self.status_label.set_text(message)
        self.status_label.set_tooltip_text('One or more albums could not be analyzed.' if errors else None)
        self._append_activity('warning' if cancelled else ('error' if errors else 'success'),
                              message, elapsed_final)
        self._append_log(f'\n{message}\n')
        # Expose measured values immediately after the scan. Open at most two
        # visible albums to preserve responsiveness with large imported queues.
        self._reveal_completed_results()
        if self._scan_wrote_tags:
            self._reload_existing_tags()
        if self.notify_switch.get_active():
            try:
                notice = Gio.Notification.new('MonkeyGain scan finished' if not cancelled
                                              else 'MonkeyGain scan cancelled')
                notice.set_body(message)
                self.get_application().send_notification('scan-finished', notice)
            except GLib.Error as exc:
                self._append_log(f'Notification unavailable: {exc}\n')
        return GLib.SOURCE_REMOVE

    def _reveal_completed_results(self):
        """Reveal the last analyzed album without rebuilding or jumping pages.

        User-initiated scrolling, search and pagination suspend auto-follow.
        Never automatically expand an unrelated album above their viewport.
        """
        if not self._follow_scan or self._last_active_folder is None:
            return
        row = self._visible_rows.get(self._last_active_folder)
        result = self._results.get(self._last_active_folder, {})
        if row is not None and (result.get('tracks') or result.get('album')):
            row['toggle'].set_active(True)
            GLib.idle_add(self._scroll_to_active_album, self._last_active_folder)

    def _refresh_tags(self, *_args):
        """Manually reload tags, without running rsgain or writing audio."""
        if self._runner.running or self._busy or not self._files:
            return
        self._busy = True
        self._set_import_sensitive(False)
        self.run_button.set_sensitive(False)
        self.scan_all_button.set_sensitive(False)
        self.status_label.set_text('Reading existing ReplayGain tags…')
        self._reload_existing_tags(manual=True)

    def _reload_existing_tags(self, *, manual: bool = False) -> None:
        """Read metadata in a worker to avoid blocking the GTK main loop."""
        files = tuple(self._files)
        generation = self._tag_generation

        def task():
            readings = load_existing_tags(files)
            GLib.idle_add(self._on_tags_reloaded, readings, generation, manual)
        threading.Thread(target=task, daemon=True).start()

    def _on_tags_reloaded(self, readings: dict[Path, TagRead], generation: int,
                          manual: bool):
        if generation != self._tag_generation:
            return GLib.SOURCE_REMOVE
        self._existing_tags.update(readings)
        if manual:
            # A manual refresh explicitly requests the on-disk values, not
            # measurements from a prior scan that might now be stale.
            self._results.clear()
        for row in self._rows:
            self._update_expander_caption(row)
            self._apply_metrics(row, self._results.get(row['folder'], {}))
            self._tag_status(row)
        tagged = sum(1 for path in self._files
                     if self._existing_tags.get(path, TagRead()).info.tagged)
        unknown = sum(1 for path in self._files
                      if self._existing_tags.get(path, TagRead()).error)
        self._append_log(f'Existing gain tags found in {tagged}/{len(self._files)} tracks'
                         f' ({unknown} unreadable).\n')
        if manual and self.tags_filter.get_selected():
            self._apply_album_filter()
        if manual:
            self._busy = False
            self._set_import_sensitive(True)
            self._update_selection_ui()
            self.status_label.set_text(f'{tagged} tracks with existing gain tags · '
                                       f'{unknown} unreadable')
        return GLib.SOURCE_REMOVE

    def _cancel_current(self, *_args):
        if self._busy:
            self._cancel_import()
        elif self._scan_started_at is not None:
            self._cancel()

    def _cancel(self, *_args):
        self._scan_cancel_requested = True
        self.status_label.set_text('Cancelling scan…')
        self._append_activity('warning', 'Cancellation requested · waiting for rsgain to stop',
                              self._log_elapsed())
        self._runner.cancel()
        self.cancel_button.set_sensitive(False)

    def _append_log(self, message: str):
        """Retain engine output internally for troubleshooting and tests."""
        self._activity_journal.add_raw(message)
        return GLib.SOURCE_REMOVE

    def _on_close(self, *_args):
        if self._runner.running:
            self._runner.cancel()
        if self._import_runner.running:
            self._import_runner.cancel()
        return False


class MonkeyGain(Gtk.Application):
    """Keep the main workspace hidden until runtime requirements are available."""

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self._runtime_status = None
        self._dependency_window = None

    def _show_dependency_error(self, message: str):
        window = Gtk.ApplicationWindow(application=self, title='MonkeyGain')
        window.set_default_size(490, 220)
        window.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(26)
        box.set_margin_bottom(26)
        box.set_margin_start(26)
        box.set_margin_end(26)
        heading = label('MonkeyGain could not start', 'mg-title', wrap=True)
        box.append(heading)
        box.append(label(message, 'mg-description', wrap=True))
        close = Gtk.Button(label='Close')
        close.set_halign(Gtk.Align.END)
        close.connect('clicked', lambda *_: window.close())
        box.append(close)
        window.set_child(box)
        self._dependency_window = window
        window.present()

    def do_activate(self):
        window = self.props.active_window
        if window:
            window.present()
            return
        if self._runtime_status is None:
            self._runtime_status = check_runtime()
        if not self._runtime_status.ready:
            self._show_dependency_error(self._runtime_status.message)
            return
        window = MonkeyGainWindow(self, self._runtime_status.backend)
        window.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        window = self.props.active_window
        if isinstance(window, MonkeyGainWindow):
            window._discover([f.get_path() for f in files if f.get_path()])


def main() -> int:
    return MonkeyGain().run(sys.argv)
