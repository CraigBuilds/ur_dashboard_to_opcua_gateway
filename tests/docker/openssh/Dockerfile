FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends openssh-server && rm -rf /var/lib/apt/lists/*

COPY sshd_config /etc/ssh/sshd_config
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && mkdir -p /run/sshd

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
