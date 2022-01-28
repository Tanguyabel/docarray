import itertools
from collections.abc import Iterable as _Iterable
from typing import (
    Sequence,
    Iterable,
    Any,
)

from ..base.getsetdel import BaseGetSetDelMixin
from .... import Document, DocumentArray


class GetSetDelMixin(BaseGetSetDelMixin):
    """Provide concrete implmentation for ``__getitem__``, ``__setitem__``,
    and ``__delitem__`` for ``DoucmentArrayWeaviate``"""

    def _getitem(self, wid: str) -> 'Document':
        """Helper method for getting item with weaviate as storage

        :param wid: weaviate id
        :raises KeyError: raise error when weaviate id does not exist in storage
        :return: Document
        """
        resp = self._client.data_object.get_by_id(wid, with_vector=True)
        if not resp:
            raise KeyError(wid)
        return Document.from_base64(
            resp['properties']['_serialized'], **self.serialize_config
        )

    def _setitem(self, wid: str, value: Document):
        """Helper method for setting an item with weaviate as storage

        :param wid: weaviate id
        :param value: the new document to update to
        """
        payload = self._doc2weaviate_create_payload(value)
        if self._client.data_object.exists(wid):
            self._client.data_object.delete(wid)
        self._client.data_object.create(**payload)
        self._offset2ids[self._offset2ids.index(wid)] = self.wmap(value.id)
        self._update_offset2ids_meta()

    def _delitem(self, wid: str):
        """Helper method for deleting an item with weaviate as storage

        :param wid: weaviate id
        """
        self._client.data_object.delete(wid)
        self._offset2ids.pop(self._offset2ids.index(wid))
        self._update_offset2ids_meta()

    def _get_doc_by_offset(self, offset: int) -> 'Document':
        """Concrete implementation of base class' ``_get_doc_by_offset``

        :param offset: the offset of the document in the list
        :return: the retrieved document from weaviate
        """
        return self._getitem(self._offset2ids[offset])

    def _get_doc_by_id(self, _id: str) -> 'Document':
        """Concrete implementation of base class' ``_get_doc_by_id``

        :param _id: the id of the document
        :return: the retrieved document from weaviate
        """
        return self._getitem(self.wmap(_id))

    def _get_docs_by_slice(self, _slice: slice) -> Iterable['Document']:
        """Concrete implementation of base class' ``_get_doc_by_slice``

        :param _slice: the slice of in the list to get docs from
        :return: an iterable of retrieved documents from weaviate
        """
        wids = self._offset2ids[_slice]
        return (self._getitem(wid) for wid in wids)

    def _set_doc_by_offset(self, offset: int, value: 'Document'):
        """Concrete implementation of base class' ``_set_doc_by_offset``

        :param offset: the offset of doc in the list to update
        :param value: the document to update to
        """
        wid = self._offset2ids[offset]
        self._setitem(wid, value)
        # update weaviate id
        self._offset2ids[offset] = self.wmap(value.id)

    def _set_doc_value_pairs(
        self, docs: Iterable['Document'], values: Sequence['Document']
    ):
        """Concrete implementation of base class' ``_set_doc_value_pairs``

        :param docs: the array of docs to update
        :param values: the values docs should be set to
        :raises ValueError: raise error when there's a mismatch between len of docs and values
        """
        # TODO: optimize/use base _set_doc_value_pairs
        docs = list(docs)
        if len(docs) != len(values):
            raise ValueError(
                f'length of docs to set({len(docs)}) does not match '
                f'length of values({len(values)})'
            )

        map_doc_id_to_offset = {doc.id: offset for offset, doc in enumerate(docs)}
        map_new_id_to_old_id = {new.id: old.id for old, new in zip(docs, values)}

        def _set_doc_value_pairs_util(_docs: DocumentArray):
            for d in _docs:
                if d.id in map_doc_id_to_offset:
                    d._data = values[map_doc_id_to_offset[d.id]]._data
                _set_doc_value_pairs_util(d.chunks)
                _set_doc_value_pairs_util(d.matches)

        res = DocumentArray(d for d in self)
        _set_doc_value_pairs_util(res)

        for r in res:
            old_id = (
                r.id if r.id not in map_new_id_to_old_id else map_new_id_to_old_id[r.id]
            )
            self._setitem(self.wmap(old_id), r)

    def _set_doc_by_id(self, _id: str, value: 'Document'):
        """Concrete implementation of base class' ``_set_doc_by_id``

        :param _id: the id of doc to update
        :param value: the document to update to
        """
        self._setitem(self.wmap(_id), value)

    def _set_docs_by_slice(self, _slice: slice, values: Sequence['Document']):
        """Concrete implementation of base class' ``_set_doc_by_slice``

        :param _slice: the slice of documents in the list to update
        :param values: the documents to update to
        :raises TypeError: error is raised if value is not an iterable because
            docs indexed by slice is always an array
        """
        wids = self._offset2ids[_slice]
        if not isinstance(values, _Iterable):
            raise TypeError('can only assign an iterable')
        for _i, _v in zip(wids, values):
            self._setitem(_i, _v)

    def _set_doc_attr_by_id(self, _id: str, attr: str, value: Any):
        """Concrete implementation of base class' ``_set_doc_attr_by_id``

        :param _id: the id of the document to update
        :param attr: the attribute to update
        :param value: the value to set doc's ``attr`` to
        :raises ValueError: raise an error if user tries to pop the id of the doc
        """
        if attr == 'id' and value is None:
            raise ValueError('pop id from Document stored with weaviate is not allowed')
        doc = self[_id]
        setattr(doc, attr, value)
        self._setitem(self.wmap(doc.id), doc)

    def _set_docs_attrs(self, docs: 'DocumentArray', attr: str, values: Iterable[Any]):
        # TODO: remove this function to use _set_doc_attr_by_id once
        # we find a way to do
        from ...memory import DocumentArrayInMemory

        if attr == 'embedding':
            docs.embeddings = values
        elif attr == 'tensor':
            docs.tensors = values
        else:
            for d, v in zip(docs, values):
                setattr(d, attr, v)

        def _set_attr_util(_docs: DocumentArrayInMemory):
            for d in _docs:
                if d in docs:
                    setattr(d, attr, getattr(docs[d.id], attr))
                _set_attr_util(d.chunks)
                _set_attr_util(d.matches)

        res = DocumentArrayInMemory([d for d in self])
        _set_attr_util(res)

        for r in res:
            self._setitem(self.wmap(r.id), r)

    def _del_doc_by_offset(self, offset: int):
        """Concrete implementation of base class' ``_del_doc_by_offset``

        :param offset: the offset of the document to delete
        """
        self._delitem(self._offset2ids[offset])

    def _del_doc_by_id(self, _id: str):
        """Concrete implementation of base class' ``_del_doc_by_id``

        :param _id: the id of the document to delete
        """
        self._delitem(self.wmap(_id))

    def _del_docs_by_slice(self, _slice: slice):
        """Concrete implementation of base class' ``_del_doc_by_slice``

        :param _slice: the slice of documents to delete
        """
        start = _slice.start or 0
        stop = _slice.stop or len(self)
        step = _slice.step or 1
        del self[list(range(start, stop, step))]

    def _del_all_docs(self):
        """ Concrete implementation of base class' ``_del_all_docs``"""
        if self._class_name:
            self._client.schema.delete_class(self._class_name)
            self._client.schema.delete_class(self._meta_name)
            self._offset2ids.clear()
            self._load_or_create_weaviate_schema(self._class_name)
            self._update_offset2ids_meta()

    def _del_docs_by_mask(self, mask: Sequence[bool]):
        """Concrete implementation of base class' ``_del_docs_by_mask``

        :param mask: the mask used for indexing which documents to delete
        """
        idxs = list(itertools.compress(self._offset2ids, (not _i for _i in mask)))
        for _idx in reversed(idxs):
            self._delitem(_idx)