#!/bin/sh
set -eu

# Configure the disposable root account before starting OpenSSH.
password="${SFTP_PASSWORD:-easybot}"
echo "root:${password}" | chpasswd

exec /usr/sbin/sshd -D -e
