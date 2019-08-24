"""
Unit tests for stem.descriptor.hidden_service for version 3.
"""

import functools
import unittest

import stem.descriptor

from stem.descriptor.hidden_service import HiddenServiceDescriptorV3

from test.unit.descriptor import (
  get_resource,
  base_expect_invalid_attr,
)

expect_invalid_attr = functools.partial(base_expect_invalid_attr, HiddenServiceDescriptorV3, 'version', 3)

EXPECTED_SIGNING_CERT = """\
-----BEGIN ED25519 CERT-----
AQgABqKwAQVql1QZETyEwJjg+Cv6f2w/cp+c3juj01NPBaJqihboAQAgBACx+FKK
oDrFE1+ztSxzN8sApKOb5UuDtoe/E03DxZU5+r/K5AV6G0hYn21V7Xbu2pZHvIkT
2oVY4hypWNJE58eFBRFRzBA0J2h0GyFs1pIuRh5QDJuxB5j92V0aRCNZFgM=
-----END ED25519 CERT-----\
"""


class TestHiddenServiceDescriptorV3(unittest.TestCase):
  def test_for_riseup(self):
    """
    Parse riseup's descriptor...

      vww6ybal4bd7szmgncyruucpgfkqahzddi37ktceo3ah7ngmcopnpyyd.onion
    """

    with open(get_resource('hidden_service_v3'), 'rb') as descriptor_file:
      desc = next(stem.descriptor.parse_file(descriptor_file, 'hidden-service-descriptor-3 1.0', validate = True))

    self.assertEqual(3, desc.version)
    self.assertEqual(180, desc.lifetime)
    self.assertEqual(EXPECTED_SIGNING_CERT, desc.signing_cert)

  def test_invalid_version(self):
    """
    Checks that our version field expects a numeric value.
    """

    test_values = (
      '',
      '-10',
      'hello',
    )

    for test_value in test_values:
      expect_invalid_attr(self, {'hs-descriptor': test_value}, 'version')

  def test_invalid_lifetime(self):
    """
    Checks that our lifetime field expects a numeric value.
    """

    test_values = (
      '',
      '-10',
      'hello',
    )

    for test_value in test_values:
      expect_invalid_attr(self, {'descriptor-lifetime': test_value}, 'lifetime')
