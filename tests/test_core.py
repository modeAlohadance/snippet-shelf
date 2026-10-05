import json
import tempfile
import unittest
from pathlib import Path
from core import Library, variables, render


class Tests(unittest.TestCase):
    def test_literal_substitution_and_cyrillic(self):
        body = '{{ имя }} / {{имя}} / {{дата}}'
        self.assertEqual(variables(body), ['имя', 'дата'])
        self.assertEqual(render(body, {'имя': r'\1{{дата}}', 'дата': 'сегодня'}), r'\1{{дата}} / \1{{дата}} / сегодня')
        with self.assertRaises(ValueError):
            render(body, {'имя': 'Анна'})

    def test_crud_search_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Library(Path(tmp) / 'db')
            record_id = library.save('Письмо', 'РАБОТА', 'Привет {{имя}}')
            self.assertEqual(len(library.search('письмо работа')), 1)
            library.save('Ответ', 'работа', 'Здравствуйте', record_id)
            self.assertEqual(library.get(record_id)['title'], 'Ответ')
            path = Path(tmp) / 'export.json'
            library.export(path)
            self.assertEqual(library.import_file(path), 1)
            library.delete(record_id)
            self.assertEqual(len(library.search()), 1)
            library.close()

    def test_invalid_import_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Library(Path(tmp) / 'db')
            path = Path(tmp) / 'bad.json'
            path.write_text(json.dumps({'version': 1, 'snippets': [{'title': 'OK', 'body': 'OK'}, {'title': '', 'body': 'bad'}]}), encoding='utf-8')
            with self.assertRaises(ValueError):
                library.import_file(path)
            self.assertEqual(library.search(), [])
            library.close()

    def test_validation(self):
        library = Library(':memory:')
        with self.assertRaises(ValueError):
            library.save('', '', 'text')
        with self.assertRaises(ValueError):
            library.save('x', '', ' '.join('{{v%d}}' % n for n in range(21)))
        library.close()
