import io
import json
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from unittest.mock import patch

import cls_telegraph as cli


def item(uid, timestamp, content='other', level='C'):
    return dict(id=uid, ctime=timestamp, content=content, title='', level=level)


class Screen:
    def __init__(self, keys):
        self.keys = iter(keys)
        self.text = []

    def getmaxyx(self):
        return 24, 80

    def getch(self):
        return next(self.keys)

    def addnstr(self, y, x, text, *args):
        self.text.append(text)

    def __getattr__(self, name):
        return lambda *args: None


class RegressionTests(unittest.TestCase):
    def run_cli(self, args, pages):
        output = io.StringIO()
        with patch('sys.argv', ['cls-telegraph', *args]), patch.object(
            cli, 'fetch_v1', side_effect=pages
        ) as fetch, redirect_stdout(output):
            cli.main()
        return fetch, json.loads(output.getvalue())

    def test_date_starts_at_next_midnight_and_includes_boundaries(self):
        start = int(datetime(2020, 1, 1).timestamp())
        end = start + 86400
        fetch, result = self.run_cli(['--date', '2020-01-01', '--json'], [
            [item(1, end - 1), item(2, start)],
        ])
        self.assertEqual(fetch.call_args_list[0].kwargs['last_time'], end)
        self.assertEqual([i['id'] for i in result], [1, 2])
        self.assertEqual(fetch.call_count, 1)

    def test_sparse_filter_reaches_fourth_page(self):
        fetch, result = self.run_cli(['-n', '1', '-k', 'target', '--json'], [
            [item(i, 100-i, 'target' if i == 4 else 'other')] for i in range(1, 5)
        ])
        self.assertEqual(result[0]['id'], 4)
        self.assertEqual(fetch.call_count, 4)

    def test_since_stops_search_without_matches(self):
        fetch, result = self.run_cli(['--since', '90', '-k', 'target', '--json'], [
            [item(1, 100)], [item(2, 90)],
        ])
        self.assertEqual(result, [])
        self.assertEqual(fetch.call_count, 2)

    def test_no_duplicate_ids_between_pages(self):
        _, result = self.run_cli(['-n', '3', '--json'], [
            [item(1, 100)], [item(1, 100), item(2, 90)], [item(3, 80)],
        ])
        self.assertEqual([i['id'] for i in result], [1, 2, 3])

    def test_stalled_cursor_fails_before_download(self):
        with patch('sys.argv', ['cls-telegraph', '--download', '--date', '2020-01-01']), patch.object(
            cli, 'fetch_v1', return_value=[item(1, int(datetime(2020, 1, 1, 12).timestamp()))]
        ), patch('builtins.open') as file_open, patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as raised:
                cli.main()
            self.assertEqual(raised.exception.code, 1)
            file_open.assert_not_called()

    def run_live(self, filters, initial, pages, keys):
        screen = Screen(keys)
        with ExitStack() as stack:
            for name in ['curs_set', 'use_default_colors', 'mousemask', 'init_pair']:
                stack.enter_context(patch.object(cli.curses, name))
            stack.enter_context(patch.object(cli.curses, 'color_pair', return_value=0))
            stack.enter_context(patch.object(cli.curses, 'wrapper', side_effect=lambda fn: fn(screen)))
            node = stack.enter_context(patch.object(cli, 'fetch_telegraph_nodeapi', return_value=initial))
            v1 = stack.enter_context(patch.object(cli, 'fetch_v1', side_effect=pages))
            cli.live_monitor(filters)
        return screen, node, v1

    def test_live_category_uses_v1_on_initial_and_periodic_refresh(self):
        screen = Screen([-1, ord('q')])
        with ExitStack() as stack:
            for name in ['curs_set', 'use_default_colors', 'mousemask', 'init_pair']:
                stack.enter_context(patch.object(cli.curses, name))
            stack.enter_context(patch.object(cli.curses, 'color_pair', return_value=0))
            stack.enter_context(patch.object(cli.curses, 'wrapper', side_effect=lambda fn: fn(screen)))
            node = stack.enter_context(patch.object(cli, 'fetch_telegraph_nodeapi'))
            v1 = stack.enter_context(patch.object(cli, 'fetch_v1', return_value=[item(1, 100, level='A')]))
            cli.live_monitor({'category': 'red'}, interval=0)
        node.assert_not_called()
        self.assertEqual(v1.call_count, 2)
        self.assertTrue(all(c.kwargs['category'] == 'red' for c in v1.call_args_list))

    def test_live_empty_and_short_filtered_pages_advance_history(self):
        screen, _, fetch = self.run_live({'keyword': 'target'}, [item(1, 100)], [
            [item(2, 90)], [item(3, 80, 'target')], [],
        ], [ord('j'), ord('j'), ord('j'), ord('j'), ord('q')])
        self.assertEqual([c.kwargs['last_time'] for c in fetch.call_args_list], [100, 90, 80])
        self.assertTrue(any('target' in text for text in screen.text))

    def test_all_outputs_preserve_distinct_body_with_shared_prefix(self):
        value = item(1, 100, 'ABCDEFGHIJKLMNOPQRST body must remain')
        value['title'] = 'ABCDEFGHIJKLMNOPQRST title'
        output = io.StringIO()
        with redirect_stdout(output):
            cli.format_terminal([value])
        rendered = [output.getvalue(),
                    cli.format_markdown([value], '2020-01-01', plain=True),
                    cli.format_markdown([value], '2020-01-01'),
                    '\n'.join(text for _, text in cli.render_item_lines(value, 100))]
        for text in rendered:
            self.assertIn('body must remain', text)

    def test_markdown_does_not_duplicate_red_heading(self):
        value = item(1, 100, 'unique body', 'A')
        self.assertEqual(cli.format_markdown([value], '2020-01-01').count('unique body'), 1)


if __name__ == '__main__':
    unittest.main()
