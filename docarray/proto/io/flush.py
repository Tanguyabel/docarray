from typing import TYPE_CHECKING, Any

from google.protobuf.struct_pb2 import Struct

from .ndarray import flush_ndarray, read_ndarray
from ..docarray_pb2 import NdArrayProto

if TYPE_CHECKING:
    from ..docarray_pb2 import DocumentProto
    from ... import Document


def parse_proto(pb_msg: 'DocumentProto') -> 'Document':
    from ... import Document
    fields = {}
    for (field, value) in pb_msg.ListFields():
        f_name = field.name
        if f_name == 'chunks' or f_name == 'matches':
            fields[f_name] = [Document.from_protobuf(d) for d in value]
        elif isinstance(value, NdArrayProto):
            fields[f_name] = read_ndarray(value)
        elif isinstance(value, Struct):
            fields[f_name] = dict(value)
        elif f_name == 'location':
            fields[f_name] = list(value)
        elif f_name == 'scores' or f_name == 'evaluations':
            ...
        else:
            fields[f_name] = value
    return Document(**fields)


def flush_proto(pb_msg: 'DocumentProto', key: str, value: Any) -> None:
    try:
        if key == 'blob' or key == 'embedding':
            pb_msg = getattr(pb_msg, key)
            flush_ndarray(pb_msg, value)
        elif key == 'chunks' or key == 'matches':
            pb_msg.ClearField(key)
            for d in value:
                d: Document
                docs = getattr(pb_msg, key)
                docs.append(d.to_protobuf())
        elif key == 'tags':
            pb_msg.tags.Clear()
            pb_msg.tags.update(value)
        else:
            # other simple fields
            setattr(pb_msg, key, value)
    except Exception as ex:
        if len(ex.args) >= 1:
            ex.args = (f'Field `{key}`',) + ex.args
        raise