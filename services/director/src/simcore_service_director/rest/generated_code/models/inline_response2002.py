# coding: utf-8

from datetime import date, datetime

from typing import List, Dict, Type

from .base_model_ import Model
from .simcore_node import SimcoreNode
from .. import util


class InlineResponse2002(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, data: List[SimcoreNode]=None, error: object=None):
        """InlineResponse2002 - a model defined in OpenAPI

        :param data: The data of this InlineResponse2002.
        :param error: The error of this InlineResponse2002.
        """
        self.openapi_types = {
            'data': List[SimcoreNode],
            'error': object
        }

        self.attribute_map = {
            'data': 'data',
            'error': 'error'
        }

        self._data = data
        self._error = error

    @classmethod
    def from_dict(cls, dikt: dict) -> 'InlineResponse2002':
        """Returns the dict as a model

        :param dikt: A dict.
        :return: The inline_response_200_2 of this InlineResponse2002.
        """
        return util.deserialize_model(dikt, cls)

    @property
    def data(self):
        """Gets the data of this InlineResponse2002.


        :return: The data of this InlineResponse2002.
        :rtype: List[SimcoreNode]
        """
        return self._data

    @data.setter
    def data(self, data):
        """Sets the data of this InlineResponse2002.


        :param data: The data of this InlineResponse2002.
        :type data: List[SimcoreNode]
        """
        if data is None:
            raise ValueError("Invalid value for `data`, must not be `None`")

        self._data = data

    @property
    def error(self):
        """Gets the error of this InlineResponse2002.


        :return: The error of this InlineResponse2002.
        :rtype: object
        """
        return self._error

    @error.setter
    def error(self, error):
        """Sets the error of this InlineResponse2002.


        :param error: The error of this InlineResponse2002.
        :type error: object
        """

        self._error = error
