# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from director.models.base_model_ import Model
from director import util


class Service(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, container_id: str=None, published_ports: List[int]=None, entry_point: str=None):  # noqa: E501
        """Service - a model defined in Swagger

        :param container_id: The container_id of this Service.  # noqa: E501
        :type container_id: str
        :param published_ports: The published_ports of this Service.  # noqa: E501
        :type published_ports: List[int]
        :param entry_point: The entry_point of this Service.  # noqa: E501
        :type entry_point: str
        """
        self.swagger_types = {
            'container_id': str,
            'published_ports': List[int],
            'entry_point': str
        }

        self.attribute_map = {
            'container_id': 'container_id',
            'published_ports': 'published_ports',
            'entry_point': 'entry_point'
        }

        self._container_id = container_id
        self._published_ports = published_ports
        self._entry_point = entry_point

    @classmethod
    def from_dict(cls, dikt) -> 'Service':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The Service of this Service.  # noqa: E501
        :rtype: Service
        """
        return util.deserialize_model(dikt, cls)

    @property
    def container_id(self) -> str:
        """Gets the container_id of this Service.

        The id of the docker container  # noqa: E501

        :return: The container_id of this Service.
        :rtype: str
        """
        return self._container_id

    @container_id.setter
    def container_id(self, container_id: str):
        """Sets the container_id of this Service.

        The id of the docker container  # noqa: E501

        :param container_id: The container_id of this Service.
        :type container_id: str
        """
        if container_id is None:
            raise ValueError("Invalid value for `container_id`, must not be `None`")  # noqa: E501

        self._container_id = container_id

    @property
    def published_ports(self) -> List[int]:
        """Gets the published_ports of this Service.

        The ports where the service provides its interface  # noqa: E501

        :return: The published_ports of this Service.
        :rtype: List[int]
        """
        return self._published_ports

    @published_ports.setter
    def published_ports(self, published_ports: List[int]):
        """Sets the published_ports of this Service.

        The ports where the service provides its interface  # noqa: E501

        :param published_ports: The published_ports of this Service.
        :type published_ports: List[int]
        """
        if published_ports is None:
            raise ValueError("Invalid value for `published_ports`, must not be `None`")  # noqa: E501

        self._published_ports = published_ports

    @property
    def entry_point(self) -> str:
        """Gets the entry_point of this Service.

        The entry point where the service provides its interface  # noqa: E501

        :return: The entry_point of this Service.
        :rtype: str
        """
        return self._entry_point

    @entry_point.setter
    def entry_point(self, entry_point: str):
        """Sets the entry_point of this Service.

        The entry point where the service provides its interface  # noqa: E501

        :param entry_point: The entry_point of this Service.
        :type entry_point: str
        """
        if entry_point is None:
            raise ValueError("Invalid value for `entry_point`, must not be `None`")  # noqa: E501

        self._entry_point = entry_point
