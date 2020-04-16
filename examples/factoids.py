import asyncio, re
from typing    import Dict, List, Optional
from irctokens import build, Line
from ircrobots import Bot     as BaseBot
from ircrobots import Server  as BaseServer
from ircrobots import ConnectionParams

TRIGGER = "!"

def _delims(s: str, delim: str):
    s_copy = list(s)
    while s_copy:
        char = s_copy.pop(0)
        if char == delim:
            if not s_copy:
                yield len(s)-(len(s_copy)+1)
            elif not s_copy.pop(0) == delim:
                yield len(s)-(len(s_copy)+2)

def _sed(sed: str, s: str) -> Optional[str]:
    if len(sed) > 1:
        delim            = sed[1]
        last             = 0
        parts: List[str] = []
        for i in _delims(sed, delim):
            parts.append(sed[last:i])
            last = i+1
            if len(parts) == 4:
                break

        pattern, replace, *args = parts
        flags_s = (args or [""])[0]

        flags = re.I if "i" in flags_s else 0
        count = 0    if "g" in flags_s else 1

        for i in reversed(list(_delims(replace, "&"))):
            replace = replace[:i] + "\\g<0>" + replace[i+1:]

        try:
            compiled = re.compile(pattern, flags)
        except:
            return None
        return re.sub(compiled, replace, s, count)
    else:
        return None

class Database:
    def __init__(self):
        self._settings: Dict[str, str] = {}

    async def get(self, context: str, setting: str) -> Optional[str]:
        return self._settings.get(setting, None)
    async def set(self, context: str, setting: str, value: str):
        self._settings[setting] = value
    async def rem(self, context: str, setting: str):
        if setting in self._settings:
            del self._settings[setting]

class Server(BaseServer):
    def __init__(self, name: str, database: Database):
        super().__init__(name)
        self._database = database

    async def line_send(self, line: Line):
        print(f"> {line.format()}")

    async def line_read(self, line: Line):
        print(f"< {line.format()}")

        me = self.nickname_lower
        if line.command == "001":
            await self.send(build("JOIN", ["##robots"]))

        if (
                line.command == "PRIVMSG" and
                self.has_channel(line.params[0]) and
                not line.hostmask is None and
                not self.casefold(line.hostmask.nickname) == me and
                self.has_user(line.hostmask.nickname) and
                line.params[1].startswith(TRIGGER)):

            channel = self.channels[self.casefold(line.params[0])]
            user    = self.users[self.casefold(line.hostmask.nickname)]
            cuser   = self.channel_users[channel][user]
            text    = line.params[1].replace(TRIGGER, "", 1)
            db_context = f"{self.name}:{channel.name}"

            name,   _, text = text.partition(" ")
            action, _, text = text.partition(" ")
            name = name.lower()
            key  = f"factoid-{name}"


            out = ""
            if not action or action == "@":
                value = await self._database.get(db_context, key)
                if not value is None:
                    out = f"({name}) {value}"
                    if action == "@" and text:
                        target, _, _ = text.partition(" ")
                        out = f"{target}: {out}"
                else:
                    out = f"{user.nickname}: '{name}' not found"

            elif action in ["==", "~="]:
                if "o" in cuser.modes:
                    value, _, _ = text.partition(" ")
                    if action == "==":
                        if value:
                            await self._database.set(db_context, key, value)
                            out = f"{user.nickname}: added factoid {name}"
                        else:
                            await self._database.rem(db_context, key)
                            out = f"{user.nickname}: removed factoid {name}"
                    elif action == "~=":
                        current = await self._database.get(db_context, key)
                        if current is None:
                            out = f"{user.nickname}: '{name}' not found"
                        elif value:
                            changed = _sed(value, current)
                            if not changed is None:
                                await self._database.set(
                                    db_context, key, changed)
                                out = (f"{user.nickname}: "
                                       f"changed '{name}' factoid")
                            else:
                                out = f"{user.nickname}: invalid sed"
                        else:
                            out = f"{user.nickname}: please provide a sed"
                else:
                    out = f"{user.nickname}: you are not an op"


            else:
                out = f"{user.nickname}: unknown action '{action}'"
            await self.send(build("PRIVMSG", [line.params[0], out]))

class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(name, Database())

async def main():
    bot = Bot()

    params = ConnectionParams(
        "robot",
        "chat.freenode.invalid",
        6697,
        tls=True)
    await bot.add_server("freenode", params)
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())