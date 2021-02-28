import textwrap

import aiohttp
import wikitextparser as wtp
from bs4 import BeautifulSoup


async def fetch_url(url):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                return text


async def get_list():
    contents = await fetch_url('https://community.bistudio.com/wiki/Category:Arma_3:_Scripting_Commands')
    soup = BeautifulSoup(contents, 'html.parser')
    links_html = soup.find(id='mw-pages').find('div', class_='mw-category-group').ul.find_all('a')
    links = {link['title']: link['href'] for link in links_html}
    return links


async def get_page(command_url_part):
    # https://community.bistudio.com/wiki?title=a_%26%26_b&action=edit
    url = 'https://community.bistudio.com/wiki?title={}&action=edit'.format(command_url_part)
    contents = await fetch_url(url)
    soup = BeautifulSoup(contents, 'html.parser')
    mediawiki = soup.find(id='wpTextbox1').text

    return mediawiki


class SQFCommand:
    def _get_plain_text(self, arg):
        if arg is None:
            return ''

        arg.get_italics()  # Workaround for a bug that makes plain_text() raise an exception
        plain = arg.plain_text()

        # Strip starting name tag
        try:
            int(arg.name)
            name = ''  # arg.name is just a positional argument, so it's not actually specified

            # Strip '|' at the start
            if plain.startswith('|'):
                plain = plain[1:]

        except ValueError:
            name = arg.name  # It's actually a string that's not a number
            prefix = f'|{name}='

            if plain.startswith(prefix):
                plain = plain[len(prefix):]

        plain = plain.strip()
        return plain

    def _parse_array(self, prefix, range_start, range_stop):
        array = []
        for i in range(range_start, range_stop):
            mw_argument = self._mw_template.get_arg(f'{prefix}{i}')

            if mw_argument:
                argument = self._get_plain_text(mw_argument)
                array.append(argument)

        return array

    def _parse_argument(self, *arg_names, default=''):
        for arg_name in arg_names:
            mw_arg = self._mw_template.get_arg(arg_name)
            if mw_arg:
                return self._get_plain_text(mw_arg)

        return default

    def __init__(self, page_name, template):
        # Based on: https://community.bistudio.com/wiki/Template:RV
        if not template.name == 'RV':
            raise ValueError(f'Tried to initialize with a bad template of: "{template.name}", expected "RV"')

        self._mw_template = template

        # Meta
        self.type = self._parse_argument('type')
        self.display_type = self._parse_argument('displayTitle', default=page_name)

        # Primary parameters
        self.game = self._parse_argument('game1', '1')
        self.version = self._parse_argument('version1', '2', default='Unknown')
        self.arg = self._parse_argument('arg')
        self.eff = self._parse_argument('arg')
        self.server_exec = self._parse_argument('serverExec')
        self.description = self._parse_argument('descr', '3', default='Description not found!')
        self.command_groups = self._parse_array('gr', 1, 6)
        self.syntax = self._parse_argument('s1', '4', default=page_name)
        self.parameters = self._parse_array('p', 1, 21)
        self.return_value = self._parse_argument('r1', '5', default='Nothing')
        self.examples = self._parse_array('x', 1, 11)
        self.see_also = self._parse_argument('seealso', '6', default='See also needed')

        # Secondary parameters
        self.multiplayer = self._parse_argument('mp')
        self.problems = self._parse_argument('pr')

        self.alt_game = self._parse_array('game', 2, 6)
        self.alt_version = self._parse_array('version', 2, 6)
        self.alt_syntax = self._parse_array('s', 2, 7)
        self.alt_parameters = [
            self._parse_array('p', 21, 41),
            self._parse_array('p', 41, 61),
            self._parse_array('p', 61, 81),
            self._parse_array('p', 81, 101),
            self._parse_array('p', 101, 121),
        ]
        self.alt_return_value = self._parse_array('r', 2, 7)

    def __str__(self):
        strings = []
        for key, val in self.__dict__.items():
            if key.startswith('_'):
                continue
            if not isinstance(val, list) or not val:  # Empty lists treat as regular values
                strings.append(f'{key}: {val}')
            else:
                strings.append(f'{key}:')
                for element in val:
                    strings.append(textwrap.indent(str(element), ' ' * (len(key) + 2)))

        return '\n'.join(strings)


def parse_mediawiki_textarea(textarea):
    parsed = wtp.parse(textarea)
    template = parsed.templates[0]
    return template
