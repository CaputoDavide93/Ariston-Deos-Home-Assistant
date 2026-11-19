# How it works

What is verified is marked as read from the library's source (`midea-beautiful-air`
0.10.7); nothing here has been run against the live cloud yet.

## Two ways to reach the device

| Route | How | Needs |
|---|---|---|
| Local (V3) | Ask the cloud for a token and key, then talk to the device on the LAN | The token call to succeed |
| Cloud | Send the status or set frame through the cloud's `transparent/send` endpoint | Internet, every call |

HA Core's Midea integration uses the local route. For this device its token call
(`/v1/iot/secure/getToken` on `mapp.appsmb.com`) answers code 9999 "system error", so
local control is not possible that way. This integration is the cloud fallback.

## The region hypothesis

The library knows two Ariston Clima servers: `mapp.appsmb.com` ("Ariston Clima", US) and
`mapp-eu.appsmb.com` ("Ariston Clima EU"). The house is in Scotland, so the account
may live on the EU server and fail on the US one. `scripts/probe.py` tries EU first, then
US, to settle it.

## How the probe asks for the token (from the library source)

1. The cloud appliance id is turned into 6 bytes, little-endian first and then big-endian.
2. Each is hashed with SHA-256; the two 16-byte halves are XORed and hex-encoded. That is the `udpid`.
3. `get_token(udpid)` posts it to `/v1/iot/secure/getToken` and picks the entry whose
   `udpId` matches; it returns that token and key, or empty strings if none matched.

## The status query

The probe builds the library's dehumidifier status frame (`DehumidifierStatusCommand`), sends
it with `appliance_transparent_send`, and decodes the reply with `DehumidifierAppliance`.
The decoded fields are power, mode (a raw number, its meaning on a Deos is not mapped),
humidity, target humidity and tank level. It sends no set command.

## Limits of the cloud path

- It needs the internet and the Midea servers up. Without them the device is unavailable.
- It polls; there is no push, so changes show up on the next poll (default 300 seconds, range 60 to 900).
- The library speaks an unofficial API. If Midea changes it, this breaks until the library is updated.
- Region, app key and login scheme are the library's choices for "Ariston Clima"; none is confirmed for any Deos until the probe passes. The owner's unit is a Deos 16S NET; the integration offers every dehumidifier (type `0xA1`) on the account, so other Deos models should appear, unconfirmed.
