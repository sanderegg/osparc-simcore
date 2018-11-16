# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from .base_model_ import Model
from .. import util


class InlineResponse2001Authors(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, affiliation=None, email=None, name=None):  # noqa: E501
        """InlineResponse2001Authors - a model defined in OpenAPI

        :param affiliation: The affiliation of this InlineResponse2001Authors.  # noqa: E501
        :type affiliation: str
        :param email: The email of this InlineResponse2001Authors.  # noqa: E501
        :type email: str
        :param name: The name of this InlineResponse2001Authors.  # noqa: E501
        :type name: str
        """
        self.openapi_types = {
            'affiliation': 'str',
            'email': 'str',
            'name': 'str'
        }

        self.attribute_map = {
            'affiliation': 'affiliation',
            'email': 'email',
            'name': 'name'
        }

        self._affiliation = affiliation
        self._email = email
        self._name = name

    @classmethod
    def from_dict(cls, dikt) -> 'InlineResponse2001Authors':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The inline_response_200_1_authors of this InlineResponse2001Authors.  # noqa: E501
        :rtype: InlineResponse2001Authors
        """
        return util.deserialize_model(dikt, cls)

    @property
    def affiliation(self):
        """Gets the affiliation of this InlineResponse2001Authors.

        Affiliation of the author  # noqa: E501

        :return: The affiliation of this InlineResponse2001Authors.
        :rtype: str
        """
        return self._affiliation

    @affiliation.setter
    def affiliation(self, affiliation):
        """Sets the affiliation of this InlineResponse2001Authors.

        Affiliation of the author  # noqa: E501

        :param affiliation: The affiliation of this InlineResponse2001Authors.
        :type affiliation: str
        """

        self._affiliation = affiliation

    @property
    def email(self):
        """Gets the email of this InlineResponse2001Authors.

        Email address  # noqa: E501

        :return: The email of this InlineResponse2001Authors.
        :rtype: str
        """
        return self._email

    @email.setter
    def email(self, email):
        """Sets the email of this InlineResponse2001Authors.

        Email address  # noqa: E501

        :param email: The email of this InlineResponse2001Authors.
        :type email: str
        """
        if email is None:
            raise ValueError("Invalid value for `email`, must not be `None`")  # noqa: E501

        self._email = email

    @property
    def name(self):
        """Gets the name of this InlineResponse2001Authors.

        Name of the author  # noqa: E501

        :return: The name of this InlineResponse2001Authors.
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this InlineResponse2001Authors.

        Name of the author  # noqa: E501

        :param name: The name of this InlineResponse2001Authors.
        :type name: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name
