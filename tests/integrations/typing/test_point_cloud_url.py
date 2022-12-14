from docarray import Document
from docarray.typing import PointCloud3DUrl


def test_set_point_cloud_url():
    class MyDocument(Document):
        point_cloud_url: PointCloud3DUrl

    d = MyDocument(point_cloud_url="https://jina.ai/mesh.obj")

    assert isinstance(d.point_cloud_url, PointCloud3DUrl)
    assert d.point_cloud_url == "https://jina.ai/mesh.obj"
