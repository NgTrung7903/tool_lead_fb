import pytest
from services.group_manager import GroupManager, normalize_group_url


def test_normalization_and_duplicates(tmp_path):
    manager = GroupManager(tmp_path / 'groups.json')
    group = manager.add_group('Test','https://m.facebook.com/groups/Test/?ref=share')
    assert group.group_url == 'https://www.facebook.com/groups/test'
    with pytest.raises(ValueError,match='đã có'):
        manager.add_group('Duplicate','http://facebook.com/groups/test')


@pytest.mark.parametrize('url',['https://evilfacebook.com/groups/a','javascript:alert(1)','https://facebook.com.evil.test/groups/a','https://facebook.com/groups/a/posts/1'])
def test_group_url_validation(url):
    with pytest.raises(ValueError): normalize_group_url(url)


def test_bulk_import_normalizes_duplicates(tmp_path):
    manager = GroupManager(tmp_path/'groups.json')
    assert manager.import_groups_from_text('Tên nhóm https://facebook.com/groups/abc/\nhttps://m.facebook.com/groups/abc?ref=share\nhttps://facebook.com/groups/def') == 2
    assert len(GroupManager(tmp_path/'groups.json').list_groups()) == 2
