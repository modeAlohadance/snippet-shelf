"""SnippetShelf editor and template composer."""
import sqlite3
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
from core import Library, variables, render
from ui import style, table, data_path


class App:
    def __init__(self, root, path):
        self.root = root
        self.library = Library(path)
        self.current = None
        self.baseline = ('', '', '')
        self.refreshing = False
        style(root, 'SnippetShelf — библиотека текстов', '#c4b5fd')
        page = ttk.Frame(root, padding=24)
        page.pack(fill='both', expand=True)
        ttk.Label(page, text='SnippetShelf', style='Title.TLabel').pack(anchor='w')
        ttk.Label(page, text='Сохраняйте формулировки. Заполняйте переменные. Копируйте результат.', style='Muted.TLabel').pack(anchor='w', pady=(0, 16))
        toolbar = ttk.Frame(page)
        toolbar.pack(fill='x')
        self.query = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.query).pack(side='left', fill='x', expand=True)
        ttk.Button(toolbar, text='Найти', command=self.refresh).pack(side='left', padx=6)
        ttk.Button(toolbar, text='Импорт JSON', command=self.import_file).pack(side='left', padx=6)
        ttk.Button(toolbar, text='Экспорт', command=self.export).pack(side='left')
        panes = ttk.Panedwindow(page, orient='horizontal')
        panes.pack(fill='both', expand=True, pady=12)
        left, right = ttk.Frame(panes), ttk.Frame(panes, padding=(18, 0, 0, 0))
        panes.add(left, weight=2)
        panes.add(right, weight=3)
        self.list = table(left, [('title', 'Название', 210), ('tags', 'Теги', 120)])
        self.list.bind('<<TreeviewSelect>>', self.select)
        ttk.Button(left, text='+ Новый шаблон', command=self.new).pack(fill='x')
        self.title, self.tags = tk.StringVar(), tk.StringVar()
        for label, value in [('Название', self.title), ('Теги — через запятую', self.tags)]:
            ttk.Label(right, text=label).pack(anchor='w', pady=(7, 3))
            ttk.Entry(right, textvariable=value).pack(fill='x')
        ttk.Label(right, text='Текст · переменные: {{имя}}, {{дата}}').pack(anchor='w', pady=(10, 4))
        self.body = ScrolledText(right, height=12, wrap='word', font=('Segoe UI', 11), bg='#182235', fg='#e5e7eb', insertbackground='white', undo=True)
        self.body.pack(fill='both', expand=True)
        actions = ttk.Frame(right)
        actions.pack(fill='x', pady=10)
        ttk.Button(actions, text='Сохранить', command=self.save).pack(side='left')
        ttk.Button(actions, text='Заполнить / копировать', command=self.compose).pack(side='left', padx=8)
        ttk.Button(actions, text='Удалить', command=self.delete).pack(side='right')
        self.status = tk.StringVar(value='Создайте шаблон или импортируйте библиотеку.')
        ttk.Label(page, textvariable=self.status, style='Muted.TLabel').pack(anchor='w')
        root.bind('<Control-s>', lambda event: self.save())
        root.bind('<Control-n>', lambda event: self.new())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def values(self):
        return self.title.get(), self.tags.get(), self.body.get('1.0', 'end-1c')

    def discard(self):
        return self.values() == self.baseline or messagebox.askyesno('Несохранённые изменения', 'Отбросить изменения текущего шаблона?', parent=self.root)

    def refresh(self):
        self.refreshing = True
        self.list.delete(*self.list.get_children())
        records = self.library.search(self.query.get())
        for row in records:
            self.list.insert('', 'end', iid=str(row['id']), values=(row['title'], row['tags']))
        if self.current is not None and self.list.exists(str(self.current)):
            self.list.selection_set(str(self.current))
        self.root.after_idle(self.end_refresh)
        self.status.set(f'Найдено шаблонов: {len(records)}. Ctrl+S — сохранить, Ctrl+N — новый.')

    def end_refresh(self):
        self.refreshing = False

    def select(self, event=None):
        selected = self.list.selection()
        if self.refreshing or not selected or int(selected[0]) == self.current:
            return
        if not self.discard():
            self.refreshing = True
            self.list.selection_remove(*selected)
            if self.current is not None and self.list.exists(str(self.current)):
                self.list.selection_set(str(self.current))
            self.root.after_idle(self.end_refresh)
            return
        record = self.library.get(int(selected[0]))
        self.load(record)

    def load(self, record=None):
        self.current = record['id'] if record else None
        self.title.set(record['title'] if record else '')
        self.tags.set(record['tags'] if record else '')
        self.body.delete('1.0', 'end')
        self.body.insert('1.0', record['body'] if record else '')
        self.body.edit_reset()
        self.baseline = self.values()

    def new(self):
        if self.discard():
            self.list.selection_remove(*self.list.selection())
            self.load()

    def save(self):
        try:
            self.current = self.library.save(*self.values(), self.current)
            self.baseline = self.values()
            self.refresh()
            self.status.set('Шаблон сохранён.')
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror('Сохранение', str(error), parent=self.root)

    def delete(self):
        if self.current is None:
            return
        if messagebox.askyesno('Удалить шаблон?', f'Удалить «{self.title.get()}»? Это действие нельзя отменить.', parent=self.root):
            try:
                self.library.delete(self.current)
                self.load()
                self.refresh()
            except sqlite3.Error as error:
                messagebox.showerror('Удаление', str(error), parent=self.root)

    def compose(self):
        body = self.values()[2]
        names = variables(body)
        if not body.strip():
            self.status.set('Сначала введите текст шаблона.')
            return
        if len(names) > 20:
            messagebox.showerror('Переменные', 'Поддерживается до 20 переменных.', parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title('Заполнить шаблон')
        window.geometry('680x620')
        window.configure(bg='#111827')
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill='both', expand=True)
        inputs = {}
        if names:
            canvas = tk.Canvas(frame, height=180, background='#111827', highlightthickness=0)
            scroll = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
            scroll.pack(side='right', fill='y')
            canvas.pack(fill='x')
            canvas.configure(yscrollcommand=scroll.set)
            fields = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=fields, anchor='nw')
            fields.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            for name in names:
                row = ttk.Frame(fields)
                row.pack(fill='x', pady=3)
                ttk.Label(row, text=name, width=18).pack(side='left')
                value = tk.StringVar()
                inputs[name] = value
                ttk.Entry(row, textvariable=value, width=42).pack(side='left')
        ttk.Label(frame, text='Результат').pack(anchor='w', pady=8)
        preview = ScrolledText(frame, wrap='word', font=('Segoe UI', 11), height=10)
        preview.pack(fill='both', expand=True)

        def update(*args):
            preview.configure(state='normal')
            preview.delete('1.0', 'end')
            preview.insert('1.0', render(body, {key: value.get() for key, value in inputs.items()}))
            preview.configure(state='disabled')

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(render(body, {key: value.get() for key, value in inputs.items()}))
            self.root.update_idletasks()
            self.status.set('Результат скопирован в буфер обмена.')
            window.destroy()

        for value in inputs.values():
            value.trace_add('write', update)
        update()
        ttk.Button(frame, text='Копировать результат', command=copy).pack(pady=(12, 0))

    def import_file(self):
        if not self.discard():
            return
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if path:
            try:
                count = self.library.import_file(path)
                self.load()
                self.refresh()
                self.status.set(f'Добавлено шаблонов: {count}.')
            except (OSError, ValueError, sqlite3.Error) as error:
                messagebox.showerror('Импорт', str(error), parent=self.root)

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='snippet-shelf.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                self.library.export(path)
                self.status.set('Сохранённые шаблоны экспортированы.')
            except (OSError, ValueError, sqlite3.Error) as error:
                messagebox.showerror('Экспорт', str(error), parent=self.root)

    def close(self):
        if self.discard():
            self.library.close()
            self.root.destroy()


def main():
    with tempfile.TemporaryDirectory(prefix='snippets-smoke-') as tmp:
        smoke = '--smoke' in sys.argv
        root = tk.Tk()
        app = App(root, Path(tmp) / 'test.db' if smoke else data_path('SnippetShelf'))
        if smoke:
            app.library.save('Приветствие', 'письма', 'Здравствуйте, {{имя}}!')
            app.refresh()
            root.after(300, app.close)
        root.mainloop()


if __name__ == '__main__':
    main()
