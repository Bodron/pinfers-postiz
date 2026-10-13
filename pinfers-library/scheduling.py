"""Build validated Postiz schedule payloads for generated clips."""

def payload(plan, media, title):
    settings = {'__type': plan['platform']}
    if plan['platform'] == 'facebook':
        settings.update(post_type='post', title=title[:255])
    elif plan['platform'] == 'tiktok':
        settings.update(content_posting_method='UPLOAD', privacy_level='SELF_ONLY',
                        duet=False, stitch=False, comment=True, autoAddMusic='no',
                        brand_content_toggle=False, brand_organic_toggle=False)
    else:
        raise ValueError('Platformă neacceptată.')
    return {'type': 'schedule', 'shortLink': False, 'date': plan['scheduled'], 'tags': [],
            'posts': [{'integration': {'id': plan['account']}, 'group': plan['id'],
                       'settings': settings, 'value': [{'content': plan['caption'],
                       'image': [{'id': media['media_id'], 'path': media['path']}]}]}]}
