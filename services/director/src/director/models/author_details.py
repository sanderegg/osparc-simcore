# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from director.models.base_model_ import Model
from director import util


class AuthorDetails(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, name: str=None, email: str=None):  # noqa: E501
        """AuthorDetails - a model defined in Swagger

        :param name: The name of this AuthorDetails.  # noqa: E501
        :type name: str
        :param email: The email of this AuthorDetails.  # noqa: E501
        :type email: str
        """
        self.swagger_types = {
            'name': str,
            'email': str
        }

        self.attribute_map = {
            'name': 'name',
            'email': 'email'
        }

        self._name = name
        self._email = email

    @classmethod
    def from_dict(cls, dikt) -> 'AuthorDetails':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The AuthorDetails of this AuthorDetails.  # noqa: E501
        :rtype: AuthorDetails
        """
        return util.deserialize_model(dikt, cls)

    @property
    def name(self) -> str:
        """Gets the name of this AuthorDetails.

        The name of the author  # noqa: E501

        :return: The name of this AuthorDetails.
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name: str):
        """Sets the name of this AuthorDetails.

        The name of the author  # noqa: E501

        :param name: The name of this AuthorDetails.
        :type name: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def email(self) -> str:
        """Gets the email of this AuthorDetails.

        The email address of the author  # noqa: E501

        :return: The email of this AuthorDetails.
        :rtype: str
        """
        return self._email

    @email.setter
    def email(self, email: str):
        """Sets the email of this AuthorDetails.

        The email address of the author  # noqa: E501

        :param email: The email of this AuthorDetails.
        :type email: str
        """
        if email is None:
            raise ValueError("Invalid value for `email`, must not be `None`")  # noqa: E501

        self._email = email
