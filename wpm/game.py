# -*- encoding: utf-8 -*-

"""
Measures your typing speed in words per minute (WPM).

This file is part of the wpm software.
Copyright 2017, 2018 Christian Stigen Larsen

Distributed under the GNU Affero General Public License (AGPL) v3 or later. See
the file LICENSE.txt for the full license text. This software makes use of open
source software.

The quotes database is *not* covered by the AGPL!
"""

import curses
import curses.ascii
import locale
import os
import sys
import time
import wpm.config
import wpm.error

def word_wrap(text, width):
    """Returns lengths of lines that can be printed without wrapping."""
    lengths = []
    while len(text) > width:
        end = text[:width + 1].rindex(" ")

        # We can't divide the input nicely, so just display it as-is
        if end == -1:
            return [len(text)]

        lengths.append(end)
        text = text[end + 1:]

    if text:
        lengths.append(len(text))

    return lengths

def screen_coords(lengths, position):
    """Translates quote offset into screen coordinates.

    Args:
        lengths: List of line lengths for the word-wrapped quote.
        position: Offset into the quote that we want to translate to screen
                  coordinates.

    Returns:
        Tuple containing X and Y screen coordinates.
    """
    y_position = 0

    for y_position, line_length in enumerate(lengths):
        if position <= line_length:
            break
        position -= line_length + 1

    return position, y_position

def pad_right(text, width):
    """Pads string with spaces on the right."""
    if len(text) < width:
        return text + " "*(width - len(text))
    return text


class Screen(object):
    """Renders the terminal screen."""

    COLOR_AUTHOR = 1
    COLOR_BACKGROUND = 2
    COLOR_CORRECT = 3
    COLOR_HISCORE = 4
    COLOR_INCORRECT = 5
    COLOR_PROMPT = 6
    COLOR_QUOTE = 7
    COLOR_STATUS = 8

    def __init__(self):
        self.config = wpm.config.Config()

        # Make delay slower
        os.environ.setdefault("ESCDELAY", self.config.escdelay)

        # I can't remember why we set LC_ALL to an empty string. Figure it out,
        # cause it doesn't look too smart.
        locale.setlocale(locale.LC_ALL, "")

        self.screen = curses.initscr()
        self.screen.nodelay(True)

        if curses.LINES < 12:
            curses.endwin()
            raise wpm.error.WpmError(
                "wpm requires at least 12 lines in your display")

        if curses.COLS < 51:
            curses.endwin()
            raise wpm.error.WpmError(
                "wpm requires at least 51 columns in your display")

        self.screen.keypad(True)
        curses.noecho()
        curses.cbreak()

        curses.start_color()
        self.set_colors()

        self.window = curses.newwin(curses.LINES, curses.COLS, 0, 0)
        self.window.keypad(True)
        self.window.timeout(self.config.window_timeout)
        self.window.bkgd(" ", Screen.COLOR_BACKGROUND)

        # TODO: Get rid of this
        self.cheight = 0

    def set_colors(self):
        """Sets up curses color pairs."""

        if os.getenv("TERM").endswith("256color"):
            bg_col = self.config.background_color_256
            curses.init_pair(Screen.COLOR_AUTHOR, *self.config.author_color_256)
            curses.init_pair(Screen.COLOR_BACKGROUND, bg_col, bg_col)
            curses.init_pair(Screen.COLOR_CORRECT, *self.config.correct_color_256)
            curses.init_pair(Screen.COLOR_HISCORE, *self.config.score_highlight_color_256)
            curses.init_pair(Screen.COLOR_INCORRECT, *self.config.incorrect_color_256)
            curses.init_pair(Screen.COLOR_PROMPT, *self.config.prompt_color_256)
            curses.init_pair(Screen.COLOR_QUOTE, *self.config.quote_color_256)
            curses.init_pair(Screen.COLOR_STATUS, *self.config.status_color_256)
        else:
            bg_col = self.config.background_color
            curses.init_pair(Screen.COLOR_AUTHOR, *self.config.author_color)
            curses.init_pair(Screen.COLOR_BACKGROUND, bg_col, bg_col)
            curses.init_pair(Screen.COLOR_CORRECT, *self.config.correct_color)
            curses.init_pair(Screen.COLOR_HISCORE, *self.config.score_highlight_color)
            curses.init_pair(Screen.COLOR_INCORRECT, *self.config.incorrect_color)
            curses.init_pair(Screen.COLOR_PROMPT, *self.config.prompt_color)
            curses.init_pair(Screen.COLOR_QUOTE, *self.config.quote_color)
            curses.init_pair(Screen.COLOR_STATUS, *self.config.status_color)

        # Rebind class variables
        Screen.COLOR_AUTHOR = curses.color_pair(Screen.COLOR_AUTHOR)
        Screen.COLOR_BACKGROUND = curses.color_pair(Screen.COLOR_BACKGROUND)
        Screen.COLOR_CORRECT = curses.color_pair(Screen.COLOR_CORRECT)
        Screen.COLOR_HISCORE = curses.color_pair(Screen.COLOR_HISCORE)
        Screen.COLOR_INCORRECT = curses.color_pair(Screen.COLOR_INCORRECT)
        Screen.COLOR_PROMPT = curses.color_pair(Screen.COLOR_PROMPT)
        Screen.COLOR_QUOTE = curses.color_pair(Screen.COLOR_QUOTE)
        Screen.COLOR_STATUS = curses.color_pair(Screen.COLOR_STATUS)

    @staticmethod
    def is_escape(key):
        """Checks for escape key."""
        if len(key) == 1:
            return ord(key) == curses.ascii.ESC
        return False

    @staticmethod
    def is_backspace(key):
        """Checks for backspace key."""
        if len(key) > 1:
            return key == "KEY_BACKSPACE"
        elif ord(key) in (curses.ascii.BS, curses.ascii.DEL):
            return True
        return False

    def get_key(self):
        """Gets a single key stroke."""
        # pylint: disable=method-hidden
        # Install a suitable get_key based on Python version
        if sys.version_info[0:2] >= (3, 3):
            self.get_key = self._get_key_py33
        else:
            self.get_key = self._get_key_py27
        return self.get_key()

    def _get_key_py33(self):
        """Python 3.3+ implementation of get_key."""
        try:
            # Curses in Python 3.3 handles unicode via get_wch
            key = self.window.get_wch()
            if isinstance(key, int):
                if key == curses.KEY_LEFT:
                    return "KEY_LEFT"
                elif key == curses.KEY_RIGHT:
                    return "KEY_RIGHT"
                elif key == curses.KEY_RESIZE:
                    return "KEY_RESIZE"
                elif key == curses.KEY_BACKSPACE:
                    return "KEY_BACKSPACE"
                return None
            return key
        except curses.error:
            return None
        except KeyboardInterrupt:
            raise

    def _get_key_py27(self):
        """Python 2.7 implementation of get_key."""
        try:
            key = self.window.getkey()

            # Start of UTF-8 multi-byte character?
            if ord(key[0]) & 0x80:
                multibyte = key[0]
                cont_bytes = ord(key[0]) << 1
                while cont_bytes & 0x80:
                    cont_bytes <<= 1
                    multibyte += self.window.getkey()[0]
                return multibyte.decode("utf-8")

            if isinstance(key, int):
                if key == curses.KEY_LEFT:
                    return "KEY_LEFT"
                elif key == curses.KEY_RIGHT:
                    return "KEY_RIGHT"
                elif key == curses.KEY_RESIZE:
                    return "KEY_RESIZE"
                return None
            return key.decode("ascii")
        except KeyboardInterrupt:
            raise
        except curses.error:
            return None

    def column(self, y, x, width, text, attr=None, left=True):
        """Writes text to screen in coumns."""
        lengths = word_wrap(text, width)

        for y, length in enumerate(lengths, y):
            if left:
                self.window.addstr(y, x, text[:length].encode("utf-8"), attr)
            else:
                self.window.addstr(y, x - length, text[:length].encode("utf-8"), attr)
            text = text[1+length:]

        return len(lengths)

    def show_quote(self, lengths, quote, color):
        for y, length in enumerate(lengths, 2):
            self.window.addstr(y, 0, quote[:length].encode("utf-8"), color)
            quote = quote[1+length:]

    def show_author(self, y_pos, right_position, author):
            self.cheight = y_pos
            self.cheight += self.column(y_pos - 1,
                                        right_position - 10,
                                        right_position // 2,
                                        author,
                                        Screen.COLOR_AUTHOR,
                                        left=False)

    def update(self, browse, head, quote, position, incorrect, author, title,
               typed, cur_wpm, average):
        """Updates the screen."""

        if self.config.max_quote_width > 0:
            quote_columns = min(curses.COLS, self.config.max_quote_width)
        else:
            quote_columns = curses.COLS

        lengths = word_wrap(quote, quote_columns - 1)
        sx, sy = screen_coords(lengths, position)
        h = len(lengths)

        # Show header
        self.window.addstr(0, 0, pad_right(head, curses.COLS),
                           Screen.COLOR_STATUS)

        if browse:
            self.show_quote(lengths, quote, Screen.COLOR_CORRECT if browse != 1
                            else Screen.COLOR_QUOTE)
            self.show_author(4 + h, quote_columns,
                             u"— %s, %s" % (author, title))

            if browse >= 2:
                typed = "You scored %.1f wpm%s " % (cur_wpm, "!" if
                                                    cur_wpm > average else ".")
            else:
                typed = ""
            typed += "Use arrows/space to browse, esc to quit, or start typing."
        elif position < len(quote):
            color = (Screen.COLOR_CORRECT if incorrect == 0 else
                     Screen.COLOR_INCORRECT)
            typed = "> " + typed

            if position + incorrect < len(quote):
                sx, sy = screen_coords(lengths, position + incorrect - 1)
                self.window.chgat(2 + sy, max(sx, 0), 1, color)

                sx, sy = screen_coords(lengths, position + incorrect)
                self.window.chgat(2 + sy, sx, 1, Screen.COLOR_QUOTE)

        # Show typed text
        if self.cheight < curses.LINES:
            self.window.move(self.cheight, 0)
            self.window.clrtoeol()
            self.window.addstr(self.cheight, 0, typed.encode("utf-8"),
                               Screen.COLOR_PROMPT)
        if browse > 1:
            # If done, highlight score
            self.window.chgat(self.cheight, 11, len(str("%.1f" % cur_wpm)),
                              Screen.COLOR_HISCORE)

        # Move cursor to current position in text before refreshing
        if browse < 1:
            sx, sy = screen_coords(lengths, position + incorrect)
            self.window.move(2 + sy, min(sx, quote_columns - 1))
        else:
            self.window.move(2, 0)

    def clear(self):
        """Clears the screen."""
        self.window.clear()

    def deinit(self):
        """Deinitializes curses."""
        curses.nocbreak()
        self.screen.keypad(False)
        curses.echo()
        curses.endwin()


class Game(object):
    """The main game runner."""
    def __init__(self, quotes, stats):
        self.config = wpm.config.Config()
        self.stats = stats
        self.average = self.stats.average(self.stats.keyboard, last_n=10)
        self.tab_spaces = None

        # Stats
        self.position = 0
        self.incorrect = 0
        self.total_incorrect = 0

        self.start = None
        self.stop = None

        self._edit = ""
        self.num_quotes = len(quotes)
        self.quotes = quotes.random_iterator()
        self.quote = self.quotes.next()

        self.screen = Screen()

    def __enter__(self):
        return self

    def __exit__(self, error_type, error_value, error_traceback):
        self.screen.deinit()
        if error_type is not None:
            return False
        else:
            return self

    def set_tab_spaces(self, spaces):
        """Sets how many spaces a tab should expand to."""
        self.tab_spaces = spaces

    def mark_finished(self):
        """Marks current race as finished."""
        self.stop = time.time()
        self.stats.add(self.wpm(self.elapsed),
                       self.accuracy,
                       self.quote.text_id,
                       self.quotes.database)

        self.average = self.stats.average(self.stats.keyboard, last_n=10)

    def run(self, to_front=None):
        """Starts the main game loop."""
        if to_front:
            self.quotes.put_to_front(to_front)
            self.quote = self.quotes._current()

        while True:
            is_typing = self.start is not None and self.stop is None

            browse = int(not is_typing)
            if self.stop is not None:
                browse = 2

            self.screen.update(browse,
                               self.get_stats(self.elapsed),
                               self.quote.text,
                               self.position,
                               self.incorrect,
                               self.quote.author,
                               self.quote.title,
                               self._edit,
                               self.wpm(self.elapsed),
                               self.average)

            key = self.screen.get_key()
            if key is not None:
                self.handle_key(key)

    def wpm(self, elapsed):
        """Words per minute."""
        if self.start is None:
            return 0
        return min((60.0 * self.position / 5.0) / elapsed, 999)

    def cps(self, elapsed):
        """Characters per second."""
        if self.start is None:
            return 0
        return min(float(self.position) / elapsed, 99)

    @property
    def elapsed(self):
        """Elapsed game round time."""
        if self.start is None:
            # Typing has not started
            return 0
        elif self.stop is None:
            # Currently typing
            return time.time() - self.start

        # Done typing
        return self.stop - self.start

    @property
    def accuracy(self):
        """Returns typing accuracy."""
        if self.start is None:
            return 0

        length = len(self.quote.text)
        return float(length) / (length + self.total_incorrect)

    def get_stats(self, elapsed):
        """Returns the top-bar stats line."""
        keyboard = self.stats.keyboard
        if keyboard is None:
            keyboard = "Unspecified"

        return "%5.1f wpm %4.1f cps %5.2fs %5.1f%% acc %5.1f avg wpm - %s" % (
            self.wpm(elapsed),
            self.cps(elapsed),
            elapsed,
            100.0*self.accuracy,
            self.average,
            keyboard)

    def reset(self, direction=0):
        """Cancels current game."""
        self.start = None
        self.stop = None

        self.position = 0
        self.incorrect = 0
        self.total_incorrect = 0

        self._edit = ""

        if direction:
            if direction > 0:
                self.quote = self.quotes.next()
            else:
                self.quote = self.quotes.previous()
            self.screen.clear()

    def resize(self):
        """Handles a resized terminal."""
        y, x = self.screen.window.getmaxyx()
        self.screen.clear()
        curses.resizeterm(y, x)

    def handle_key(self, key):
        """Dispatches actions based on key and current mode."""
        if key == "KEY_RESIZE":
            self.resize()
            return

        # Browse mode
        if self.start is None or (self.start is not None and
                                  self.stop is not None):
            if key in (" ", "KEY_LEFT", "KEY_RIGHT"):
                self.reset(direction=-1 if key == "KEY_LEFT" else 1)
                return
            elif Screen.is_escape(key):
                # Exit program
                raise KeyboardInterrupt()

        if Screen.is_escape(key):
            self.reset()
            return

        if Screen.is_backspace(key):
            if self.incorrect:
                self.incorrect -= 1
                self._edit = self._edit[:-1]
            elif self._edit:
                self.position -= 1
                self._edit = self._edit[:-1]
            return

        # Try again?
        if self.stop is not None:
            self.reset()
            self.screen.clear()
            self.screen.update(1,
                               self.get_stats(self.elapsed),
                               self.quote.text,
                               self.position,
                               self.incorrect,
                               self.quote.author,
                               self.quote.title,
                               self._edit,
                               self.wpm(self.elapsed),
                               self.average)

        # Start recording upon first ordinary key press
        if self.start is None:
            self.start = time.time()

        if key == curses.KEY_ENTER:
            key = "\n"
        elif key == "\t" and self.tab_spaces is not None:
            key = " "*self.tab_spaces

        # Did the user strike the correct key?
        if self.incorrect == 0 and self.quote.text[self.position] == key:
            self.position += 1

            # Reset edit buffer on a correctly finished word
            if key == " " or key == "\n":
                self._edit = ""
            else:
                self._edit += key

            # Finished typing?
            if self.position == len(self.quote.text):
                self.mark_finished()
        elif self.incorrect + self.position < len(self.quote.text):
            self.incorrect += 1
            self.total_incorrect += 1
            if key == "\n":
                key = " "
            self._edit += key
