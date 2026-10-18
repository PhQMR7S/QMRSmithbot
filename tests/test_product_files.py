from aiogram.types import Message

from qmrsmithbot.telegram.product_runtime import FILE_METHODS, file_reference


def test_media_references_preserve_telegram_type_without_download_or_factory_size_cap():
    message=Message.model_validate({'message_id':1,'date':0,'chat':{'id':42,'type':'private'},
        'animation':{'file_id':'animated','file_unique_id':'a','width':10,'height':10,'duration':1},
        'document':{'file_id':'animated','file_unique_id':'a','file_size':999999999},'caption':'Caption'})
    assert file_reference(message)=={'file_type':'animation','file_id':'animated','caption':'Caption'}
    assert FILE_METHODS['video_note']=='sendVideoNote'


def test_photo_uses_the_largest_reference():
    message=Message.model_validate({'message_id':1,'date':0,'chat':{'id':42,'type':'private'},
        'photo':[{'file_id':'small','file_unique_id':'s','width':1,'height':1},
                 {'file_id':'large','file_unique_id':'l','width':100,'height':100}]})
    assert file_reference(message)['file_id']=='large'
