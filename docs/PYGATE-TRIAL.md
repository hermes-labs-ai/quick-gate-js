# Primitive adapter compatibility

The earlier PyGate 0.1.2 adapter rejection is historical. That package lacked the
argv, timeout, external-output, stable-version, and shared-result properties
HermesGate requires.

HermesGate 0.1.2 accepts only explicit, preinstalled adapters that meet these
floors:

- PyGate 0.2.0 or newer
- QuickGate.js 0.2.3 or newer

Both must emit a valid `gate-result/v1` document. The adapter is disabled by
default, does not install packages, and writes its changed-file input and result
artifacts under `.git/hermes-gate/adapters/`. An unavailable binary, an old
version, a malformed result, or a non-passing result cannot become a HermesGate
PASS receipt.

Repository-native commands remain the zero-dependency default.
