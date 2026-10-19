# Local MinIO images from pinned official source

The example environment can build its storage prerequisites locally when the
upstream image distribution is unavailable. These are the unmodified official
MinIO server and client sources, not a replacement S3 implementation.

Requires Python 3.12+, Go 1.24.2 (or a compatible newer compiler), and Docker. Source/module downloads use the host
network. Image construction only copies static binaries into `busybox:1.36`;
there are no Dockerfile network commands. Cache that base image first if Docker
cannot reach its registry.

```sh
python3 containers/minio-source/build.py --images
# On x86 hosts (choose the architecture of the Docker engine):
python3 containers/minio-source/build.py --arch amd64 --images
python3 -m unittest discover -s containers/minio-source -p 'test_*.py' -v
```

The command creates these local images:

- `datapipe-minio:RELEASE.2025-09-07T16-13-09Z`
- `datapipe-mc:RELEASE.2025-08-13T08-35-41Z`

The default target follows the host architecture (`arm64`/`aarch64` or
`x86_64`/`amd64`). Use `--arch` if the Docker engine runs a different architecture.
Docker image metadata is set to the same Linux architecture as the compiled binary.

`--component minio` and `--component mc` build only one component. Omit `--images`
to compile binaries without invoking Docker. No Go executable is installed into
your `GOBIN`; downloads use the usual Go module cache. `-mod=readonly` preserves
upstream dependency versions and the standard Go checksum verification remains
enabled. `CGO_ENABLED=0` creates static Linux binaries.

Source archives are fetched exclusively from the official GitHub repositories
at the immutable commits below. A pinned SHA256 is checked on every invocation,
including cached archives. Incorrect archives, downloads, compilation or Docker
build failures terminate the command with nonzero status. Do not hand-edit the
ignored `build/` sources; rerun the builder to re-extract the verified archive.

| Component | Official source commit | Archive SHA256 |
| --- | --- | --- |
| minio | `07c3a429bfed433e49018cb0f78a52145d4bedeb` | `8819e3e7817e46b7b3798f8f200ead208562e571563c2e040352378031abe9f2` |
| mc | `7394ce0dd2a80935aded936b09fa12cbb3cb8096` | `95cd293c7119f16921a6dc515a1fb74a2227f19fd994b9c8b770a154e802ac44` |

Official source links:

- https://github.com/minio/minio/tree/07c3a429bfed433e49018cb0f78a52145d4bedeb
- https://github.com/minio/mc/tree/7394ce0dd2a80935aded936b09fa12cbb3cb8096

The upstream annotated release tags resolved to these commits when implemented;
the builder uses the immutable commits, not mutable tag resolution. Both projects
are licensed under GNU AGPLv3. Their upstream LICENSE is copied into each image
at `/usr/share/licenses/<component>/LICENSE`. Corresponding source remains in
`build/<component>-<commit>/` after compilation and is available at the exact
links above. Keep corresponding source and license obligations in mind if
redistributing these local images.

Repeated runs verify the source archive and reuse a compiled binary only when
its recorded source commit, archive checksum, architecture, compiler version and
current binary checksum match. Docker still verifies/builds its cached image
layers. Delete `build/` to force a complete local rebuild.

Each build writes `<component>-provenance.json` containing source URL/hash,
commit, binary hash, target architecture and Go version. It is copied into the
image at `/usr/share/<component>/provenance.json`. Build binaries, downloaded
sources and reports are ignored by Git. The Docker base tag and compiler version
can affect output bytes; the binary checksum records what was actually built.

The server entrypoint is `/usr/bin/minio`, and the client is `/usr/bin/mc`.
BusyBox provides `/bin/sh` and `wget`; it does not provide `curl`. Server health
can be checked with `wget -q -O /dev/null http://localhost:9000/minio/health/live`.
