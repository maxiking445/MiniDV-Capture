"""Read preferences saved before the interface switched to English."""


def english_options(options):
    result = dict(options)
    if result.get('format') == 'AVI / DV verlustfrei':
        result['format'] = 'AVI / DV lossless'
    if 'quality' in result:
        result['quality'] = {'Hoch': 'High', 'Kompakt': 'Compact'}.get(result['quality'], result['quality'])
    return result
