FROM busybox:1.36
COPY build/minio /usr/bin/minio
COPY build/minio-LICENSE /usr/share/licenses/minio/LICENSE
COPY build/minio-provenance.json /usr/share/minio/provenance.json
EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
