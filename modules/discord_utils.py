def escape_markdown(text, language=''):
    prefix = f'```{language}\n'
    suffix = '```'
    ellipsis = '(...)'

    if text == '':
        return '```\n```'  # Otherwise, Discord treats "sqf" as the message contents

    retval = '{}{}{}'.format(prefix, text, suffix)
    if len(retval) > 2000:
        allowed_length = 2000 - len(ellipsis) - len(prefix) - len(suffix)
        text = text[:allowed_length] + ellipsis  # "longtexthere" -> "longte(...)"
        retval = '{}{}{}'.format(prefix, text, suffix)

    return retval
