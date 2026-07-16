#!/bin/sh
set -eu

password="${SFTP_PASSWORD:-easybot}"
echo "root:${password}" | chpasswd

exec /usr/sbin/sshd -D -e
