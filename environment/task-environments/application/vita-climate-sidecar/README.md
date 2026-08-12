# Vita climate sidecar

Stateful HTTP simulation of Vita climate control. The Playground starts this
service with Apple Container and publishes it on `127.0.0.1:8907`.

The launcher stages Linux/arm64 dependencies with `uv` before building, so the
Apple Container BuildKit VM does not need direct package-index access.
