"""Presentation rows: one identifiable customer across source posts.

Collection history remains comment-based. Anonymous and unknown authors are
kept separate because a shared display label does not identify a person.
"""
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit
import re


def post_key(row):
    value = row.get('source_url') or ''
    if value:
        from services.facebook_comment_collector import normalize_post_url
        try:
            return normalize_post_url(value)
        except ValueError:
            return value
    return row.get('posting_task_id') or '__unspecified__'


def _identity(row, index):
    if row.get('identity_status') != 'known':
        return ('unknown', index)
    profile = row.get('fb_user_url')
    if profile:
        u = urlsplit(profile)
        if u.scheme != 'https' or u.hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com') or u.username:
            profile = None
    if profile:
        path = u.path.rstrip('/')
        uid = parse_qs(u.query).get('id', [None])[0]
        if path == '/profile.php' and uid:
            return ('profile-id', uid)
        if path.strip('/').isdigit():
            return ('profile-id', path.strip('/'))
        parts = path.split('/')
        if (len(parts) == 5 and parts[1] == 'groups' and parts[3] == 'user') or path.startswith('/people/'):
            return ('profile-id', parts[-1])
        return ('profile', path.casefold())
    name = (row.get('fb_user_name') or '').strip().casefold()
    return ('name', name) if name else ('unknown', index)


def aggregate_customers(records):
    groups = {}
    originals = [comment for row in records for comment in (row.get('comments') or [row])]
    for index, row in enumerate(originals):
        identity = _identity(row, index)
        # A display name alone can refer to different people in different groups.
        key = identity if identity[0].startswith('profile') else (post_key(row), identity)
        groups.setdefault(key, []).append(row)
    result = []
    rank = {'LEAD_POTENTIAL': 2, 'NEEDS_REVIEW': 1, 'IGNORE': 0}
    for comments in groups.values():
        # Retain the strongest individual assessment, without adding scores
        # merely because a person comments more often.
        best = max(comments, key=lambda r: (rank.get(r.get('classification'), 0), r.get('score', 0)))
        row = deepcopy(best)
        row['comments'] = deepcopy(comments)
        row['comment_count'] = len(comments)
        sources = {}
        for comment in comments:
            source = {k: comment.get(k) for k in ('source_url', 'group_name', 'campaign_id', 'posting_task_id', 'campaign_title', 'listing_source_url')}
            path = urlsplit(comment.get('source_url') or '').path
            match = re.match(r'^/groups/([^/]+)', path)
            source['group_key'] = ('https://www.facebook.com/groups/' + match[1]) if match else (comment.get('group_name') or '__external__')
            sources.setdefault((post_key(comment), comment.get('campaign_id'), comment.get('posting_task_id')), source)
        row['sources'] = list(sources.values())
        row['group_count'] = len({source['group_key'] for source in row['sources']})
        row['last_collected_at'] = max((c.get('last_collected_at') or '' for c in comments), default='') or None
        row['raw_content'] = '\n\n'.join(c.get('raw_content') or c.get('text') or '' for c in comments)
        row['comment_url'] = '\n'.join(dict.fromkeys(c['comment_url'] for c in comments if c.get('comment_url')))
        contacts = row.setdefault('contacts', {})
        for field in ('primary_phone', 'zalo'):
            values = list(dict.fromkeys(c.get('contacts', {}).get(field) for c in comments if c.get('contacts', {}).get(field)))
            contacts[field] = '\n'.join(values) or None
        contacts['emails'] = list(dict.fromkeys(e for c in comments for e in c.get('contacts', {}).get('emails', [])))
        row['contact_channels'] = list(dict.fromkeys(ch for c in comments for ch in c.get('contact_channels', [])))
        result.append(row)
    return result
