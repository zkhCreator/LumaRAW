# Publication allowlist for the rawpy wheel workflow

The isolated wheel workflow contains only these reviewed source files under
`scripts/rawpy-wheel/`:

- `build_rawpy_wheel.py`
- `requirements.in`
- `requirements.lock`
- `toolchain.cmake`
- `verify-wheel.py`
- `patches/rawpy-greybox.patch`
- `patches/rawpy-cmake-toolchain.patch`
- `patches/libraw-greybox-validity.patch`
- `README.md`
- `PUBLICATION_ALLOWLIST.md`

Keep the following out of the repository: downloaded third-party source
archives, extracted source trees, CMake/build output, generated wheels,
virtual environments, logs, machine-specific SDK/tool paths, RAW fixtures,
credentials, and private verification receipts. The `--work` directory must
remain outside the checkout and is never part of this allowlist.

The builder verifies reviewed patch hashes before any build. Upstream licenses
remain under `licenses/`; project build documentation records the command.
A patch/hash mismatch must fail closed.
