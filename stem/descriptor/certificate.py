# Copyright 2017, Damian Johnson and The Tor Project
# See LICENSE for licensing information

"""
Parsing for the Tor server descriptor Ed25519 Certificates, which is used to
validate the Ed25519 key used to sign the relay descriptor.

Certificates can optionally contain CertificateExtension objects depending on
their type and purpose. Currently Ed25519KeyCertificate certificates will
contain one SignedWithEd25519KeyCertificateExtension.

**Module Overview:**

::

  Certificate - Tor Certificate
    +- Ed25519KeyCertificate - Certificate for Ed25519 signing key
       +- verify_descriptor_signature - verify a relay descriptor against a signature

  CertificateExtension - Certificate extension
    +- SignedWithEd25519KeyCertificateExtension - Ed25519 signing key extension
"""

import base64
import binascii
import hashlib
import time

import stem.prereq
import stem.util.str_tools

try:
  # added in python 2.7
  from collections import OrderedDict
except ImportError:
  from stem.util.ordereddict import OrderedDict

SIGNATURE_LENGTH = 64
STANDARD_ATTRIBUTES_LENGTH = 40
CERTIFICATE_FLAGS_LENGTH = 4
ED25519_ROUTER_SIGNATURE_PREFIX = b'Tor router descriptor signature v1'


def _bytes_to_long(b):
  if stem.prereq.is_python_3():
    return int(binascii.hexlify(stem.util.str_tools._to_bytes(b)), 16)
  else:
    return long(binascii.hexlify(b), 16)


def _parse_long_offset(offset, length):
  def _parse(raw_contents):
    return _bytes_to_long(raw_contents[offset:(offset + length)])

  return _parse


def _parse_offset(offset, length):
  def _parse(raw_contents):
    return raw_contents[offset:(offset + length)]

  return _parse


def _parse_certificate(raw_contents, master_key_bytes, validate = False):
  version = raw_contents[0:1]
  cert_type = raw_contents[1:2]

  if version == b'\x01':
    if cert_type == b'\x04':
      return Ed25519KeyCertificate(raw_contents, master_key_bytes, validate = validate)
    elif cert_type == b'\x05':
      # TLS link certificated signed with ed25519 signing key
      pass
    elif cert_type == b'\x06':
      # Ed25519 authentication signed with ed25519 signing key
      pass
    else:
      raise ValueError("Unknown Certificate type %s" % binascii.hexlify(cert_type))
  else:
    raise ValueError("Unknown Certificate version %s" % binascii.hexlify(version))


def _parse_extensions(raw_contents):
  n_extensions = _bytes_to_long(raw_contents[39:40])
  if n_extensions == 0:
    return []

  extensions = []
  extension_bytes = raw_contents[STANDARD_ATTRIBUTES_LENGTH:-SIGNATURE_LENGTH]

  while len(extension_bytes) > 0:
    ext_length = _bytes_to_long(extension_bytes[0:2])
    ext_type = extension_bytes[2:3]
    ext_flags = extension_bytes[3:CERTIFICATE_FLAGS_LENGTH]
    ext_data = extension_bytes[CERTIFICATE_FLAGS_LENGTH:(CERTIFICATE_FLAGS_LENGTH + ext_length)]
    if len(ext_type) == 0 or len(ext_flags) == 0 or len(ext_data) == 0:
      raise ValueError('Certificate contained truncated extension')

    if ext_type == SignedWithEd25519KeyCertificateExtension.TYPE:
      extension = SignedWithEd25519KeyCertificateExtension(ext_type, ext_flags, ext_data)
    else:
      raise ValueError('Invalid certificate extension type: %s' % binascii.hexlify(ext_type))

    extensions.append(extension)
    extension_bytes = extension_bytes[CERTIFICATE_FLAGS_LENGTH + ext_length:]

  if len(extensions) != n_extensions:
    raise ValueError('n_extensions was %d but parsed %d' % (n_extensions, len(extensions)))

  return extensions


def _parse_signature(cert):
  return cert[-SIGNATURE_LENGTH:]


class Certificate(object):
  """
  See proposal #220 <https://gitweb.torproject.org/torspec.git/tree/proposals/220-ecc-id-keys.txt>
  """

  ATTRIBUTES = {
    'version': _parse_offset(0, 1),
    'cert_type': _parse_offset(1, 1),
    'expiration_date': _parse_long_offset(2, 4),
    'cert_key_type': _parse_offset(6, 1),
    'certified_key': _parse_offset(7, 32),
    'n_extensions': _parse_long_offset(39, 1),
    'extensions': _parse_extensions,
    'signature': _parse_signature
  }

  def __init__(self, raw_contents, identity_key, validate = False):
    self.certificate_bytes = raw_contents

    if type(identity_key) == bytes:
      self.identity_key = stem.util.str_tools._to_unicode(identity_key)
    else:
      self.identity_key = identity_key

    self.__set_certificate_entries(raw_contents)

  def __set_certificate_entries(self, raw_contents):
    entries = OrderedDict()
    for key, func in Certificate.ATTRIBUTES.items():
      try:
        entries[key] = func(raw_contents)
      except IndexError:
        raise ValueError('Unable to get bytes for %s from certificate' % key)

    for key, value in entries.items():
      setattr(self, key, value)


class Ed25519KeyCertificate(Certificate):
  def __init__(self, raw_contents, identity_key, validate = False):
    super(Ed25519KeyCertificate, self).__init__(raw_contents, identity_key, validate = False)

    if validate:
      if len(self.extensions) == 0:
        raise ValueError('Ed25519KeyCertificate missing SignedWithEd25519KeyCertificateExtension extension')

      self._verify_signature()

      if (self.expiration_date * 3600) < int(time.time()):
        raise ValueError('Expired Ed25519KeyCertificate')

  def verify_descriptor_signature(self, descriptor, signature):
    if not stem.prereq._is_pynacl_available():
      raise ValueError('Certificate validation requires the pynacl module')

    import nacl.signing
    from nacl.exceptions import BadSignatureError

    missing_padding = len(signature) % 4
    signature_bytes = base64.b64decode(stem.util.str_tools._to_bytes(signature) + b'=' * missing_padding)
    verify_key = nacl.signing.VerifyKey(self.certified_key)

    signed_part = descriptor[:descriptor.index(b'router-sig-ed25519 ') + len('router-sig-ed25519 ')]
    descriptor_with_prefix = ED25519_ROUTER_SIGNATURE_PREFIX + signed_part
    descriptor_sha256_digest = hashlib.sha256(descriptor_with_prefix).digest()

    try:
      verify_key.verify(descriptor_sha256_digest, signature_bytes)
    except BadSignatureError:
      raise ValueError('Descriptor Ed25519 certificate signature invalid')

  def _verify_signature(self):
    if not stem.prereq._is_pynacl_available():
      raise ValueError('Certificate validation requires the pynacl module')

    import nacl.signing
    import nacl.encoding
    from nacl.exceptions import BadSignatureError

    if self.identity_key:
      verify_key = nacl.signing.VerifyKey(self.identity_key + '=', encoder=nacl.encoding.Base64Encoder)
    else:
      verify_key = nacl.singing.VerifyKey(self.extensions[0].ext_data)

    try:
      verify_key.verify(self.certificate_bytes[:-SIGNATURE_LENGTH], self.signature)
    except BadSignatureError:
      raise ValueError('Ed25519KeyCertificate signature invalid')


class CertificateExtension(object):
  KNOWN_TYPES = [b'\x04']

  def __init__(self, ext_type, ext_flags, ext_data):
    self.ext_type = ext_type
    self.ext_flags = ext_flags
    self.ext_data = ext_data

  def is_known_type(self):
    return self.ext_type in CertificateExtension.KNOWN_TYPES

  def affects_validation(self):
    return self.ext_flags == b'\x01'


class SignedWithEd25519KeyCertificateExtension(CertificateExtension):
  TYPE = b'\x04'

  def __init__(self, ext_type, ext_flags, ext_data):
    super(SignedWithEd25519KeyCertificateExtension, self).__init__(ext_type, ext_flags, ext_data)
