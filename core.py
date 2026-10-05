"""Local snippet library and literal, non-executable variable substitution."""
import json
import re
import sqlite3
from datetime import datetime

TOKEN = re.compile(r'\{\{\s*([\w-]+)\s*\}\}', re.UNICODE)


def variables(body):
    return list(dict.fromkeys(TOKEN.findall(body)))


def render(body, values):
    missing = [name for name in variables(body) if name not in values]
    if missing:
        raise ValueError('Не заполнены переменные: ' + ', '.join(missing))
    return TOKEN.sub(lambda match: str(values[match.group(1)]), body)


def validate(record):
    if not isinstance(record, dict):
        raise ValueError('Каждая запись должна быть объектом.')
    result = {}
    for key, limit in [('title', 200), ('tags', 500), ('body', 100_000)]:
        value = record.get(key, '' if key == 'tags' else None)
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'Некорректное поле {key}: ожидается текст длиной до {limit}.')
        result[key] = value.strip() if key != 'body' else value
    if not result['title'] or not result['body'].strip():
        raise ValueError('Название и текст не могут быть пустыми.')
    if len(variables(result['body'])) > 20:
        raise ValueError('Поддерживается до 20 переменных в одном шаблоне.')
    return result


class Library:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS snippets (id INTEGER PRIMARY KEY, title TEXT NOT NULL, tags TEXT NOT NULL, body TEXT NOT NULL, updated TEXT NOT NULL)')
        self.db.commit()

    def save(self, title, tags, body, record_id=None):
        item = validate(dict(title=title, tags=tags, body=body))
        values = (item['title'], item['tags'], item['body'], datetime.now().isoformat(timespec='seconds'))
        with self.db:
            if record_id is None:
                return self.db.execute('INSERT INTO snippets (title,tags,body,updated) VALUES (?,?,?,?)', values).lastrowid
            self.db.execute('UPDATE snippets SET title=?,tags=?,body=?,updated=? WHERE id=?', (*values, record_id))
            return record_id

    def search(self, query=''):
        # casefold handles Cyrillic, unlike SQLite's default ASCII-only LIKE.
        terms = query.casefold().split()
        rows = self.db.execute('SELECT * FROM snippets ORDER BY updated DESC, id DESC')
        return [dict(row) for row in rows if all(term in (row['title'] + ' ' + row['tags'] + ' ' + row['body']).casefold() for term in terms)]

    def get(self, record_id):
        row = self.db.execute('SELECT * FROM snippets WHERE id=?', (record_id,)).fetchone()
        return dict(row) if row else None

    def delete(self, record_id):
        with self.db:
            self.db.execute('DELETE FROM snippets WHERE id=?', (record_id,))

    def export(self, path):
        from pathlib import Path
        records = [{key: row[key] for key in ('title', 'tags', 'body')} for row in self.search()]
        if len(records) > 1000:
            raise ValueError('Для JSON-экспорта поддерживается до 1000 записей. Полная библиотека остаётся в локальной базе SQLite.')
        payload = json.dumps({'version': 1, 'snippets': records}, ensure_ascii=False, indent=2)
        if len(payload.encode('utf-8')) > 5_000_000:
            raise ValueError('JSON-экспорт превышает 5 МБ. Полная библиотека остаётся в локальной базе SQLite.')
        Path(path).write_text(payload, encoding='utf-8')

    def import_file(self, path):
        with open(path, 'rb') as source:
            raw = source.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError('Файл больше 5 МБ.')
        data = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Ожидается экспорт SnippetShelf версии 1.')
        records = data.get('snippets')
        if not isinstance(records, list) or len(records) > 1000:
            raise ValueError('Ожидается список не более 1000 шаблонов.')
        checked = [validate(record) for record in records]
        now = datetime.now().isoformat(timespec='seconds')
        with self.db:
            self.db.executemany('INSERT INTO snippets (title,tags,body,updated) VALUES (?,?,?,?)',
                                [(r['title'], r['tags'], r['body'], now) for r in checked])
        return len(checked)

    def close(self):
        self.db.close()
