# A throwaway Linux host with systemd and polkit, for tests/linux-grants.sh:
#   podman build -t hearth-linux -f tests/linux.Containerfile tests
#   podman run -d --name hearth-linux --privileged --systemd=always \
#     -v $PWD:/src:ro -v <frontdesk checkout>:/fd:ro hearth-linux
#   podman exec hearth-linux bash /src/tests/linux-grants.sh; podman rm -f hearth-linux
FROM docker.io/library/python:3.12-slim
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq systemd systemd-sysv dbus polkitd curl >/dev/null && rm -rf /var/lib/apt/lists/*
CMD ["/lib/systemd/systemd"]
