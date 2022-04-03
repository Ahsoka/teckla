from discord_slash.utils.manage_commands import create_option as og_create_option

import types
import typing
import discord

def create_option(
    name: str,
    description: str,
    option_type: typing.Union[int, type],
    required: bool,
    choices: list = None,
) -> dict:
    options = og_create_option(
        name,
        description,
        option_type,
        required,
        choices
    )
    channel = types.SimpleNamespace(_type=0)
    if (
        isinstance(option_type, type)
        and issubclass(option_type, discord.abc.GuildChannel)
        and hasattr(option_type, 'type')
    ):
        options['channel_types'] = [option_type.type.fget(channel).value]

    return options
