FROM busybox:1.36
COPY build/mc /usr/bin/mc
COPY build/mc-LICENSE /usr/share/licenses/mc/LICENSE
COPY build/mc-provenance.json /usr/share/mc/provenance.json
ENTRYPOINT ["/usr/bin/mc"]
