"""MonkeyGain native GTK 4 desktop application."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk, Gdk

from . import __version__
from .core import (
    ScanRunner, ScanSettings, backend_version, discover_audio,
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
        self.set_default_size(1120, 740)
        self.set_size_request(800, 580)
        self._files: set[Path] = set()
        self._rows: list[tuple[Gtk.Label, Gtk.Image]] = []
        self._jobs = []
        self._busy = False
        self._settings = self._read_settings()
        self._runner = ScanRunner(
            lambda line: GLib.idle_add(self._append_log, line),
            lambda idx, status: GLib.idle_add(self._on_job, idx, status),
            lambda ok, err, canceled: GLib.idle_add(self._on_finished, ok, err, canceled),
        )
        self.connect('close-request', self._on_close)
        self._init_css()
        self._create_widgets()
        self._set_appearance(self._settings.get('theme', 'dark'))
        version = backend_version()
        if version:
            self.engine_label.set_text(f'rsgain {version} conectado')
            self.engine_label.add_css_class('mg-ok')
        else:
            self.engine_label.set_text('rsgain no encontrado — instálalo para analizar')
            self.engine_label.add_css_class('mg-error')
            self.run_button.set_sensitive(False)
        self._update_collection()
        self._append_log(f'MonkeyGain {__version__} · Listo para analizar.\n')

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

        header = Gtk.HeaderBar()
        header.add_css_class('mg-header')
        head_title = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        image = Gtk.Picture.new_for_filename(str(ASSET_DIR / 'monkeygain.svg'))
        image.set_size_request(32, 32)
        image.set_content_fit(Gtk.ContentFit.CONTAIN)
        head_title.append(image)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        titles.append(label('MonkeyGain', 'mg-brand'))
        titles.append(label('ReplayGain Studio', 'mg-muted-small'))
        head_title.append(titles)
        header.set_title_widget(head_title)
        self.add_folder_button = button('Carpeta', 'folder-open-symbolic', self._choose_folder)
        self.add_file_button = button('Archivos', 'list-add-symbolic', self._choose_files)
        self.clear_button = button('Limpiar', 'edit-clear-all-symbolic', self._clear)
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
        headings.append(label('Tu biblioteca', 'mg-title'))
        headings.append(label('Importa álbumes y analiza su volumen sin modificar el audio.', 'mg-description', wrap=True))
        overview.append(headings)
        self.count_label = label('0 álbumes · 0 pistas', 'mg-count')
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
        logs_header.append(label('Registro de análisis', 'mg-section'))
        space = Gtk.Box()
        space.set_hexpand(True)
        logs_header.append(space)
        logs_header.append(button('Exportar', 'document-save-symbolic', self._export_log))
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
        sidebar.append(label('Configuración', 'mg-title'))
        sidebar.append(label('Perfil personalizado · rsgain custom', 'mg-description'))
        self.config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        sidebar.append(self.config_box)

        self.loud_spin = Gtk.SpinButton.new_with_range(-30, -5, 1)
        self.loud_spin.set_value(int(self._settings.get('loudness', -18)))
        self._field('Loudness objetivo', self.loud_spin, 'LUFS')
        self.peak_spin = Gtk.SpinButton.new_with_range(-20, 0, 0.5)
        self.peak_spin.set_digits(1)
        self.peak_spin.set_value(float(self._settings.get('max_peak', -1)))
        self._field('Pico máximo', self.peak_spin, 'dB')
        self.clip_choice = Gtk.DropDown.new_from_strings([
            'Solo ganancia positiva', 'Protección siempre', 'Sin protección',
        ])
        clip = self._settings.get('clip_mode', 'p')
        self.clip_choice.set_selected({'p': 0, 'a': 1, 'n': 2}.get(clip, 0))
        self.config_box.append(self._plain_field('Protección contra clipping', self.clip_choice))
        sidebar.append(Gtk.Separator())

        self.album_switch = self._switch('Album Gain', 'Calcula una ganancia común por carpeta',
                                         bool(self._settings.get('album', True)), sidebar)
        self.true_peak_switch = self._switch('True Peak', 'Detecta picos entre muestras',
                                             bool(self._settings.get('true_peak', True)), sidebar)
        self.write_switch = self._switch('Escribir etiquetas', 'Desactiva para analizar sin guardar cambios',
                                         bool(self._settings.get('write_tags', True)), sidebar)
        self.skip_switch = self._switch('Omitir pistas etiquetadas', 'Conservar ReplayGain existente',
                                        bool(self._settings.get('skip_existing', False)), sidebar)
        sidebar.append(Gtk.Separator())
        self.theme_choice = Gtk.DropDown.new_from_strings(['Sistema', 'Claro', 'Oscuro'])
        self.theme_choice.set_selected({'system': 0, 'light': 1, 'dark': 2}.get(
            self._settings.get('theme', 'dark'), 2))
        sidebar.append(self._plain_field('Apariencia', self.theme_choice))
        sidebar.append(label('Los álbumes se agrupan por carpeta. No mezcles discos distintos en una carpeta.',
                             'mg-hint', wrap=True))

        for control in (self.loud_spin, self.peak_spin):
            control.connect('value-changed', self._save_settings)
        for control in (self.album_switch, self.true_peak_switch, self.write_switch, self.skip_switch):
            control.connect('notify::active', self._save_settings)
        self.clip_choice.connect('notify::selected', self._save_settings)
        self.theme_choice.connect('notify::selected', self._theme_changed)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.set_margin_start(22)
        footer.set_margin_end(22)
        footer.set_margin_top(10)
        footer.set_margin_bottom(12)
        footer.add_css_class('mg-footer')
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_hexpand(True)
        self.status_label = label('Listo · Selecciona archivos o carpetas', 'mg-description')
        status_box.append(self.status_label)
        self.engine_label = label('Comprobando motor…', 'mg-muted-small')
        status_box.append(self.engine_label)
        footer.append(status_box)
        self.progress = Gtk.ProgressBar()
        self.progress.set_size_request(170, -1)
        self.progress.set_valign(Gtk.Align.CENTER)
        self.progress.set_show_text(True)
        self.progress.set_fraction(0)
        self.progress.set_text('0 % · álbumes')
        footer.append(self.progress)
        self.cancel_button = button('Cancelar', 'process-stop-symbolic', self._cancel)
        self.cancel_button.set_sensitive(False)
        footer.append(self.cancel_button)
        self.run_button = button('Iniciar análisis', 'media-playback-start-symbolic', self._confirm_start, 'mg-primary')
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
        block.append(label('Tu música empieza aquí', 'mg-section', xalign=0.5))
        block.append(label('Usa «Archivos» o «Carpeta» para crear la cola.', 'mg-description', xalign=0.5))
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

    def _choose_files(self, *_args):
        dialog = Gtk.FileDialog()
        dialog.set_title('Seleccionar canciones')
        dialog.open_multiple(self, None, self._on_files_selected)

    def _on_files_selected(self, dialog, result):
        try:
            model = dialog.open_multiple_finish(result)
            files = [model.get_item(n).get_path() for n in range(model.get_n_items())]
        except GLib.Error as exc:
            if not exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self._append_log(f'No se pudieron seleccionar archivos: {exc}\n')
            return
        self._discover(files)

    def _choose_folder(self, *_args):
        dialog = Gtk.FileDialog()
        dialog.set_title('Seleccionar carpeta de música')
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error as exc:
            if not exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self._append_log(f'No se pudo seleccionar la carpeta: {exc}\n')
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
        self.status_label.set_text('Buscando archivos compatibles…')

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
            self._append_log(f'Error al importar: {error}\n')
        old = len(self._files)
        self._files.update(new_files)
        self.status_label.set_text(f'{len(self._files) - old} archivos nuevos añadidos')
        if not new_files:
            self._append_log('No se encontraron archivos compatibles con rsgain 3.4.\n')
        self._update_collection()
        return GLib.SOURCE_REMOVE

    def _clear(self, *_args):
        if self._runner.running or self._busy:
            return
        self._files.clear()
        self._update_collection()
        self.status_label.set_text('Lista vacía')

    def _remove_folder(self, _button, folder: Path):
        if self._runner.running or self._busy:
            return
        self._files = {file for file in self._files if file.parent != folder}
        self._update_collection()

    def _update_collection(self):
        self._jobs = make_album_jobs(self._files)
        self._rows.clear()
        while row := self.album_list.get_row_at_index(0):
            self.album_list.remove(row)
        ntracks = sum(len(job.files) for job in self._jobs)
        self.count_label.set_text(f'{len(self._jobs)} álbum(es) · {ntracks} pistas')
        for job in self._jobs:
            item = Gtk.ListBoxRow()
            item.add_css_class('mg-album-row')
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_start(14)
            row.set_margin_end(12)
            row.set_margin_top(11)
            row.set_margin_bottom(11)
            row.append(Gtk.Image.new_from_icon_name('folder-music-symbolic'))
            lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            lines.set_hexpand(True)
            name_label = label(elide(job.label, 70), 'mg-album-title')
            name_label.set_tooltip_text(str(job.folder))
            lines.append(name_label)
            formats = ', '.join(sorted({p.suffix[1:].upper() for p in job.files}))
            info = f'{len(job.files)} pistas · {formats}'
            lines.append(label(elide(info, 60), 'mg-muted-small'))
            row.append(lines)
            status_icon = Gtk.Image.new_from_icon_name('content-loading-symbolic')
            status_icon.set_visible(False)
            row.append(status_icon)
            status = label('Pendiente', 'mg-status')
            row.append(status)
            remove = Gtk.Button.new_from_icon_name('window-close-symbolic')
            remove.set_tooltip_text('Quitar álbum de la lista')
            remove.add_css_class('flat')
            remove.connect('clicked', self._remove_folder, job.folder)
            row.append(remove)
            item.set_child(row)
            self.album_list.append(item)
            self._rows.append((status, status_icon))
        if not self._runner.running:
            self.progress.set_fraction(0)
            self.progress.set_text('0 % · álbumes')
            self.run_button.set_sensitive(bool(self._jobs) and backend_version() is not None)

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
            text='¿Escribir etiquetas ReplayGain?',
        )
        dialog.props.secondary_text = (
            f'rsgain actualizará los metadatos de {sum(len(j.files) for j in self._jobs)} '
            'archivos. Las muestras de audio no cambiarán, pero se modificarán las etiquetas. '
            'Es recomendable probar primero con una copia de un álbum.'
        )
        dialog.add_button('Cancelar', Gtk.ResponseType.CANCEL)
        dialog.add_button('Escribir etiquetas', Gtk.ResponseType.ACCEPT)
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
        for status, image in self._rows:
            status.set_text('Pendiente')
            image.set_visible(False)
        self.progress.set_fraction(0)
        self.progress.set_text('0 % · álbumes')
        self.run_button.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        self._set_import_sensitive(False)
        self.config_box.set_sensitive(False)
        self.album_switch.set_sensitive(False)
        self.true_peak_switch.set_sensitive(False)
        self.write_switch.set_sensitive(False)
        self.skip_switch.set_sensitive(False)
        self.status_label.set_text('Iniciando análisis…')
        try:
            self._runner.start(list(self._jobs), config)
        except Exception as exc:
            self._append_log(f'No se pudo iniciar: {exc}\n')
            self._on_finished(0, 1, False)

    def _set_import_sensitive(self, active: bool):
        self.add_folder_button.set_sensitive(active)
        self.add_file_button.set_sensitive(active)
        self.clear_button.set_sensitive(active)

    def _on_job(self, index: int, status: str):
        mapping = {
            'running': ('Analizando…', 'media-playback-start-symbolic'),
            'success': ('Completado', 'emblem-ok-symbolic'),
            'failed': ('Error', 'dialog-error-symbolic'),
            'cancelled': ('Cancelado', 'process-stop-symbolic'),
        }
        if index >= len(self._rows):
            return GLib.SOURCE_REMOVE
        caption, icon_name = mapping.get(status, ('Pendiente', 'content-loading-symbolic'))
        item, image = self._rows[index]
        item.set_text(caption)
        image.set_from_icon_name(icon_name)
        image.set_visible(True)
        if status != 'running':
            finished = sum(label_.get_text() in ('Completado', 'Error', 'Cancelado') for label_, _ in self._rows)
            self.progress.set_fraction(finished / len(self._rows))
            self.progress.set_text(f'{finished}/{len(self._rows)} álbumes')
        else:
            self.status_label.set_text(f'Analizando {index + 1}/{len(self._rows)}: {self._jobs[index].label}')
        return GLib.SOURCE_REMOVE

    def _on_finished(self, success: int, errors: int, cancelled: bool):
        self.config_box.set_sensitive(True)
        self.album_switch.set_sensitive(True)
        self.true_peak_switch.set_sensitive(True)
        self.write_switch.set_sensitive(True)
        self.skip_switch.set_sensitive(True)
        self._set_import_sensitive(True)
        self.cancel_button.set_sensitive(False)
        self.run_button.set_sensitive(bool(self._jobs))
        if cancelled:
            message = f'Cancelado · {success} álbumes completados, {errors} con error'
        else:
            message = f'Finalizado · {success} álbumes completados, {errors} con error'
            self.progress.set_fraction(1)
            self.progress.set_text('Proceso terminado')
        self.status_label.set_text(message)
        self._append_log(f'\n{message}\n')
        return GLib.SOURCE_REMOVE

    def _cancel(self, *_args):
        self.status_label.set_text('Solicitando cancelación…')
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
        dialog.set_title('Guardar registro')
        dialog.set_initial_name('monkeygain-log.txt')
        dialog.save(self, None, self._on_log_saved)

    def _on_log_saved(self, dialog, result):
        try:
            file = dialog.save_finish(result)
            path = file.get_path()
            if not path:
                raise OSError('Selecciona una ubicación local.')
            buffer = self.log_view.get_buffer()
            text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            Path(path).write_text(text, encoding='utf-8')
            self.status_label.set_text('Registro exportado correctamente')
        except GLib.Error:
            return
        except OSError as exc:
            self._append_log(f'No se pudo exportar el registro: {exc}\n')

    def _on_close(self, *_args):
        if self._runner.running:
            self._runner.cancel()
        return False


class MonkeyGain(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.monkeygain.MonkeyGain',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        window = self.props.active_window
        if not window:
            window = MonkeyGainWindow(self)
        window.present()


def main() -> int:
    return MonkeyGain().run(None)
