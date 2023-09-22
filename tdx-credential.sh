#!/bin/bash

# 建議先在保密安全的他處設定：
# export TDX_ID=xxxxxx-xxxxxxxx-xxxx-xxxx
# export TDX_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# export TDX_TOKEN_DIR=$HOME/.cache/tdx/

# https://github.com/httpie/httpie/issues/150
# http -f POST --ignore-stdin 'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token' content-type:application/x-www-form-urlencoded grant_type=client_credentials client_id=$TDX_ID client_secret=$TDX_SECRET > $TDX_TOKEN_DIR/tdx-credential.json

curl --request POST \
    --url 'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token' \
    --header content-type:application/x-www-form-urlencoded \
    --data grant_type=client_credentials \
    --data client_id=$TDX_ID \
    --data client_secret=$TDX_SECRET \
    > $TDX_TOKEN_DIR/tdx-credential.json

export TDX_ACCESS_TOKEN=$(jq .access_token $TDX_TOKEN_DIR/tdx-credential.json | sed 's/"//g')

