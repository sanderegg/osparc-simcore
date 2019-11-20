# coding: utf-8

"""
    Director API

    This is the oSparc's director API  # noqa: E501

    The version of the OpenAPI document: 0.1.0
    Contact: support@simcore.com
    Generated by: https://openapi-generator.tech
"""


import pprint
import re  # noqa: F401

import six

from simcore_director_sdk.configuration import Configuration


class InlineResponse2002Badges(object):
    """NOTE: This class is auto generated by OpenAPI Generator.
    Ref: https://openapi-generator.tech

    Do not edit the class manually.
    """

    """
    Attributes:
      openapi_types (dict): The key is attribute name
                            and the value is attribute type.
      attribute_map (dict): The key is attribute name
                            and the value is json key in definition.
    """
    openapi_types = {
        'image': 'str',
        'name': 'str',
        'url': 'str'
    }

    attribute_map = {
        'image': 'image',
        'name': 'name',
        'url': 'url'
    }

    def __init__(self, image=None, name=None, url=None, local_vars_configuration=None):  # noqa: E501
        """InlineResponse2002Badges - a model defined in OpenAPI"""  # noqa: E501
        if local_vars_configuration is None:
            local_vars_configuration = Configuration()
        self.local_vars_configuration = local_vars_configuration

        self._image = None
        self._name = None
        self._url = None
        self.discriminator = None

        self.image = image
        self.name = name
        self.url = url

    @property
    def image(self):
        """Gets the image of this InlineResponse2002Badges.  # noqa: E501

        Url to the shield  # noqa: E501

        :return: The image of this InlineResponse2002Badges.  # noqa: E501
        :rtype: str
        """
        return self._image

    @image.setter
    def image(self, image):
        """Sets the image of this InlineResponse2002Badges.

        Url to the shield  # noqa: E501

        :param image: The image of this InlineResponse2002Badges.  # noqa: E501
        :type: str
        """
        if self.local_vars_configuration.client_side_validation and image is None:  # noqa: E501
            raise ValueError("Invalid value for `image`, must not be `None`")  # noqa: E501

        self._image = image

    @property
    def name(self):
        """Gets the name of this InlineResponse2002Badges.  # noqa: E501

        Name of the subject  # noqa: E501

        :return: The name of this InlineResponse2002Badges.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this InlineResponse2002Badges.

        Name of the subject  # noqa: E501

        :param name: The name of this InlineResponse2002Badges.  # noqa: E501
        :type: str
        """
        if self.local_vars_configuration.client_side_validation and name is None:  # noqa: E501
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def url(self):
        """Gets the url of this InlineResponse2002Badges.  # noqa: E501

        Link to status  # noqa: E501

        :return: The url of this InlineResponse2002Badges.  # noqa: E501
        :rtype: str
        """
        return self._url

    @url.setter
    def url(self, url):
        """Sets the url of this InlineResponse2002Badges.

        Link to status  # noqa: E501

        :param url: The url of this InlineResponse2002Badges.  # noqa: E501
        :type: str
        """
        if self.local_vars_configuration.client_side_validation and url is None:  # noqa: E501
            raise ValueError("Invalid value for `url`, must not be `None`")  # noqa: E501

        self._url = url

    def to_dict(self):
        """Returns the model properties as a dict"""
        result = {}

        for attr, _ in six.iteritems(self.openapi_types):
            value = getattr(self, attr)
            if isinstance(value, list):
                result[attr] = list(map(
                    lambda x: x.to_dict() if hasattr(x, "to_dict") else x,
                    value
                ))
            elif hasattr(value, "to_dict"):
                result[attr] = value.to_dict()
            elif isinstance(value, dict):
                result[attr] = dict(map(
                    lambda item: (item[0], item[1].to_dict())
                    if hasattr(item[1], "to_dict") else item,
                    value.items()
                ))
            else:
                result[attr] = value

        return result

    def to_str(self):
        """Returns the string representation of the model"""
        return pprint.pformat(self.to_dict())

    def __repr__(self):
        """For `print` and `pprint`"""
        return self.to_str()

    def __eq__(self, other):
        """Returns true if both objects are equal"""
        if not isinstance(other, InlineResponse2002Badges):
            return False

        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        if not isinstance(other, InlineResponse2002Badges):
            return True

        return self.to_dict() != other.to_dict()
