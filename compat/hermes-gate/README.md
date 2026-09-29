# Historical Hermes Gate Action

`action.yml` is byte-for-byte the public Action at core commit
`91fd282405a0b4edec2354ec2bfeb08de1679292` and tag `v0.1.7`:
SHA-256 `f3139bb8d4fd00d058a84cd00f6b76e7a6d888b795ba77716faef98f865de14c`.
Its install-version guard and offline regression tests preserve the publication lesson.
This snapshot is not a new supported Action path or a default to bump for each release.

Existing users resolve the original `hermes-labs-ai/hermes-gate@REF` repository.
Keeping this fixture does not preserve that public path or establish rename compatibility.
The new source-pinned Action is `../../.github/actions/kwik-e-gate`, with its own
`mode` input and receipt outputs. See [migration](../../docs/MIGRATION.md).
