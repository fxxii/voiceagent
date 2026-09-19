#!/bin/sh
set -eu

uuid=${1:?usage: $0 <channel-uuid> [websocket-base-url]}
base_url=${2:-wss://voice.fxxii.com/v1/audio}
secret_file=${MEDIA_SECRET_FILE:-/etc/freeswitch/edge-hmac.secret}
signer=${MEDIA_SIGNER:-/usr/local/bin/freeswitch-media-auth}

timestamp=$(date +%s)
nonce="${uuid}-${timestamp}-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
signature=$($signer --secret-file "$secret_file" "$uuid" "$timestamp" "$nonce")

headers=$(printf '{"X-Call-ID":"%s","X-Timestamp":"%s","X-Nonce":"%s","Authorization":"FS-HMAC %s"}' \
  "$uuid" "$timestamp" "$nonce" "$signature")
metadata=$(printf '{"call_id":"%s","audio_format":"L16","sample_rate":8000,"channels":1}' "$uuid")

sudo fs_cli -x "uuid_setvar $uuid STREAM_EXTRA_HEADERS '$headers'"
sudo fs_cli -x "uuid_setvar $uuid STREAM_BUFFER_SIZE 20"
sudo fs_cli -x "uuid_setvar $uuid STREAM_HEART_BEAT 20"
sudo fs_cli -x "uuid_setvar $uuid STREAM_MESSAGE_DEFLATE 1"
sudo fs_cli -x "uuid_audio_stream $uuid start ${base_url%/}/$uuid mono 8000 $metadata"
